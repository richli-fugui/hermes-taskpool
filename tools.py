"""Hermes Agent tools for the shared project task pool."""

from __future__ import annotations

import json
from typing import Any, Callable

from . import store


def _schema(name: str, description: str, properties: dict[str, Any], required=None) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        parameters["required"] = required
    return {"name": name, "description": description, "parameters": parameters}


_TASK_INPUT = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": store.MAX_TITLE_LENGTH},
        "notes": {"type": "string", "maxLength": store.MAX_NOTES_LENGTH},
        "status": {"type": "string", "enum": sorted(store.STATUSES)},
    },
    "required": ["title"],
    "additionalProperties": False,
}

_LIST_SCHEMA = _schema(
    "task_pool_list",
    "Read the shared Task Pool for the Hermes project that owns this Agent session's current working directory. "
    "Use this first for natural-language requests such as ‘整理一下任务卡’ or ‘查看任务卡’. In this product, 任务卡 means this Task Pool, not Hermes Kanban or todo_list. "
    "No project ID or path is accepted from tool arguments; an unregistered or ambiguous project fails closed.",
    {},
)
_ADD_SCHEMA = _schema(
    "task_pool_add",
    "Create 1–50 cards in the shared task pool for the current registered Hermes project. "
    "Call task_pool_list first to review existing cards and avoid duplicates; after writing, call task_pool_list again to verify project, cards, revisions, and count. "
    "Prefer small cards: each card is one completable step with a concrete action in the title and acceptance criteria in notes. "
    "If one card would need multiple steps, sessions, or people, split it into separate cards; use one card per minimal next action instead of an umbrella task. "
    "This only records work; it never dispatches or starts a task. Use request_key to make a retry idempotent. "
    "No project ID or path is accepted; project identity comes from the calling session cwd.",
    {
        "tasks": {"type": "array", "items": _TASK_INPUT, "minItems": 1, "maxItems": 50},
        "request_key": {"type": "string", "maxLength": 200},
    },
    required=["tasks"],
)
_UPDATE_SCHEMA = _schema(
    "task_pool_update",
    "Update title, notes, or status on one card in the current registered Hermes project. "
    "For task-card organization, call task_pool_list first, then pass the card's current revision; after writing, call task_pool_list again to verify. Stale updates are rejected instead of overwriting newer edits. "
    "Cards cannot be deleted through this tool, and changes never dispatch work.",
    {
        "task_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "expected_revision": {"type": "integer", "minimum": 1},
        "title": {"type": "string", "minLength": 1, "maxLength": store.MAX_TITLE_LENGTH},
        "notes": {"type": "string", "maxLength": store.MAX_NOTES_LENGTH},
        "status": {"type": "string", "enum": sorted(store.STATUSES)},
    },
    required=["task_id", "expected_revision"],
)


def _resolve_current_project(ctx):
    cwd = str(ctx.session_cwd() or "").strip()
    if not cwd:
        raise ValueError("项目身份未确认，拒绝写入")
    from hermes_cli import projects_db

    with projects_db.connect_closing() as conn:
        project = projects_db.project_for_path(conn, cwd)
    if project is None or project.archived:
        raise ValueError("项目身份未确认，拒绝写入")
    path = project.primary_path or next(
        (folder.path for folder in project.folders if folder.is_primary), None
    )
    if not path:
        raise ValueError("项目身份未确认，拒绝写入")
    return project


def _project_fields(project) -> tuple[str, str, str]:
    project_id = str(getattr(project, "id", "") or "").strip()
    name = str(getattr(project, "name", "") or "").strip()
    path = str(getattr(project, "primary_path", "") or "").strip()
    if not path:
        path = next(
            (str(folder.path) for folder in getattr(project, "folders", []) if folder.is_primary), ""
        )
    if not project_id or not name or not path:
        raise ValueError("项目身份未确认，拒绝写入")
    return project_id, name, path


def _json_result(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


_ERROR_META: list[tuple[str, str, str]] = [
    ("项目身份未确认", "PROJECT_IDENTITY_UNCONFIRMED",
     "Register the directory in Hermes Projects, then start a new session inside the registered path. Do not pass a project ID or path."),
    ("任务卡已被修改", "REVISION_CONFLICT",
     "Call task_pool_list to read the card's current revision, then retry with that value."),
    ("未找到该项目任务卡", "TASK_NOT_FOUND",
     "Call task_pool_list to get the current card IDs for this project."),
    ("相同请求键已用于不同的任务内容", "IDEMPOTENCY_CONFLICT",
     "Reuse the request_key only for an identical payload; otherwise send a new request_key."),
]


def _error_meta(exc: Exception) -> dict[str, str]:
    message = str(exc)
    for needle, code, hint in _ERROR_META:
        if needle in message:
            return {"code": code, "hint": hint}
    return {"code": "VALIDATION_ERROR",
            "hint": "Fix the issue described in the error and retry; nothing was written."}


def register_tools(
    ctx,
    *,
    project_resolver: Callable | None = None,
    db_opener: Callable | None = None,
) -> None:
    """Register tool handlers; optional dependencies exist only to support isolated tests."""
    resolve = project_resolver or _resolve_current_project
    open_db = db_opener or store.open_db

    def with_project(write: bool):
        project = resolve(ctx)
        if project is None or getattr(project, "archived", False):
            raise ValueError("项目身份未确认，拒绝写入")
        project_id, project_name, project_path = _project_fields(project)
        conn = open_db()
        if write:
            store.ensure_board(conn, project_id, project_name, project_path)
        return conn, project, project_id

    def handle_list(args: dict[str, Any], **_kwargs) -> str:
        conn = None
        try:
            conn, project, project_id = with_project(write=False)
            board = store.read_board(conn, project_id)
            board["project"] = {"id": project_id, "name": str(project.name)}
            return _json_result({"ok": True, **board})
        except Exception as exc:
            return _json_result({"ok": False, "error": str(exc), **_error_meta(exc)})
        finally:
            if conn is not None:
                conn.close()

    def handle_add(args: dict[str, Any], **_kwargs) -> str:
        conn = None
        try:
            conn, _project, project_id = with_project(write=True)
            result = store.add_tasks(
                conn,
                project_id,
                args.get("tasks"),
                request_key=args.get("request_key"),
            )
            return _json_result({"ok": True, "project_id": project_id, **result})
        except Exception as exc:
            return _json_result({"ok": False, "error": str(exc), **_error_meta(exc)})
        finally:
            if conn is not None:
                conn.close()

    def handle_update(args: dict[str, Any], **_kwargs) -> str:
        conn = None
        try:
            conn, _project, project_id = with_project(write=True)
            changes = {key: args[key] for key in ("title", "notes", "status") if key in args}
            result = store.update_task(
                conn,
                project_id,
                args.get("task_id", ""),
                changes,
                expected_revision=args.get("expected_revision"),
            )
            return _json_result({"ok": True, "project_id": project_id, **result})
        except Exception as exc:
            return _json_result({"ok": False, "error": str(exc), **_error_meta(exc)})
        finally:
            if conn is not None:
                conn.close()

    for name, schema, handler, emoji in (
        ("task_pool_list", _LIST_SCHEMA, handle_list, "📋"),
        ("task_pool_add", _ADD_SCHEMA, handle_add, "➕"),
        ("task_pool_update", _UPDATE_SCHEMA, handle_update, "✏️"),
    ):
        ctx.register_tool(
            name=name,
            toolset="project_task_pool",
            schema=schema,
            handler=handler,
            emoji=emoji,
        )
