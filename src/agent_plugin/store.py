"""Profile-scoped SQLite store shared by the task-pool Agent tools and desktop API."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


STATUSES = frozenset({"todo", "doing", "blocked", "review", "done"})
MAX_TITLE_LENGTH = 240
MAX_NOTES_LENGTH = 20000


class TaskPoolError(Exception):
    """Base class for expected task-pool errors."""


class TaskNotFound(TaskPoolError):
    pass


class RevisionConflict(TaskPoolError):
    pass


class IdempotencyConflict(TaskPoolError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS task_pool_boards (
            project_id TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            project_path TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_pool_tasks (
            project_id TEXT NOT NULL,
            id TEXT NOT NULL,
            title TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK (status IN ('todo','doing','blocked','review','done')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (project_id, id),
            FOREIGN KEY (project_id) REFERENCES task_pool_boards(project_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS task_pool_requests (
            project_id TEXT NOT NULL,
            request_key TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (project_id, request_key)
        );
        CREATE TABLE IF NOT EXISTS task_pool_legacy_imports (
            project_id TEXT NOT NULL,
            source_key TEXT NOT NULL,
            result_json TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            PRIMARY KEY (project_id, source_key)
        );
        CREATE TABLE IF NOT EXISTS task_pool_legacy_conflicts (
            project_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            source_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            PRIMARY KEY (project_id, task_id, source_key)
        );
        """
    )
    conn.commit()


def open_db() -> sqlite3.Connection:
    """Open Hermes' profile-scoped database and ensure this plugin's schema exists."""
    from plugins.plugin_storage import plugin_db

    conn = plugin_db("pp-pane")
    init_db(conn)
    return conn


def ensure_board(
    conn: sqlite3.Connection, project_id: str, project_name: str, project_path: str
) -> None:
    if not all(isinstance(v, str) and v.strip() for v in (project_id, project_name, project_path)):
        raise ValueError("项目身份未确认，拒绝写入")
    now = _now()
    with conn:
        conn.execute(
            """INSERT INTO task_pool_boards(project_id, project_name, project_path, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(project_id) DO UPDATE SET
                 project_name=excluded.project_name,
                 project_path=excluded.project_path,
                 updated_at=excluded.updated_at""",
            (project_id, project_name.strip(), project_path, now),
        )


def _task_dict(row: sqlite3.Row | tuple) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        get = row.__getitem__
    else:
        keys = ("id", "title", "notes", "status", "created_at", "updated_at", "revision")
        values = dict(zip(keys, row))
        get = values.__getitem__
    return {
        "id": get("id"),
        "title": get("title"),
        "notes": get("notes"),
        "status": get("status"),
        "createdAt": get("created_at"),
        "updatedAt": get("updated_at"),
        "revision": get("revision"),
    }


def read_board(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    board = conn.execute(
        "SELECT project_id, project_name, project_path, revision, updated_at "
        "FROM task_pool_boards WHERE project_id=?",
        (project_id,),
    ).fetchone()
    rows = conn.execute(
        "SELECT id, title, notes, status, created_at, updated_at, revision "
        "FROM task_pool_tasks WHERE project_id=? ORDER BY created_at DESC, id",
        (project_id,),
    ).fetchall()
    project = None if board is None else {
        "id": board["project_id"],
        "name": board["project_name"],
        "path": board["project_path"],
    }
    return {
        "project": project,
        "revision": 0 if board is None else board["revision"],
        "updatedAt": None if board is None else board["updated_at"],
        "tasks": [_task_dict(row) for row in rows],
    }


def _normalize_new_task(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        raise ValueError("任务卡格式异常，未写入")
    title = item.get("title")
    notes = item.get("notes", "")
    status = item.get("status", "todo")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > MAX_TITLE_LENGTH:
        raise ValueError("任务标题不能为空且不得超过 240 个字符")
    if not isinstance(notes, str) or len(notes) > MAX_NOTES_LENGTH:
        raise ValueError("任务说明格式异常或超过长度限制")
    if status not in STATUSES:
        raise ValueError("任务状态无效")
    return {"title": title.strip(), "notes": notes, "status": status}


def add_tasks(
    conn: sqlite3.Connection,
    project_id: str,
    items: list[dict[str, Any]],
    request_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(items, list) or not items or len(items) > 50:
        raise ValueError("一次必须提供 1–50 张任务卡")
    normalized = [_normalize_new_task(item) for item in items]
    payload_hash = hashlib.sha256(_json(normalized).encode("utf-8")).hexdigest()
    if request_key is not None and (
        not isinstance(request_key, str) or not request_key.strip() or len(request_key) > 200
    ):
        raise ValueError("幂等请求键无效")

    with conn:
        if request_key:
            prior = conn.execute(
                "SELECT payload_hash, result_json FROM task_pool_requests "
                "WHERE project_id=? AND request_key=?",
                (project_id, request_key),
            ).fetchone()
            if prior:
                if prior[0] != payload_hash:
                    raise IdempotencyConflict("相同请求键已用于不同的任务内容")
                return json.loads(prior[1])

        now = _now()
        tasks = [
            {
                "id": uuid.uuid4().hex,
                **item,
                "createdAt": now,
                "updatedAt": now,
                "revision": 1,
            }
            for item in normalized
        ]
        conn.executemany(
            """INSERT INTO task_pool_tasks
               (project_id, id, title, notes, status, created_at, updated_at, revision)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (project_id, t["id"], t["title"], t["notes"], t["status"],
                 t["createdAt"], t["updatedAt"], t["revision"])
                for t in tasks
            ],
        )
        conn.execute(
            "UPDATE task_pool_boards SET revision=revision+1, updated_at=? WHERE project_id=?",
            (now, project_id),
        )
        result = {"tasks": tasks, "boardRevision": _board_revision(conn, project_id)}
        if request_key:
            conn.execute(
                "INSERT INTO task_pool_requests(project_id, request_key, payload_hash, result_json, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (project_id, request_key, payload_hash, _json(result), now),
            )
        return result


def update_task(
    conn: sqlite3.Connection,
    project_id: str,
    task_id: str,
    changes: dict[str, Any],
    *,
    expected_revision: int,
) -> dict[str, Any]:
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 1:
        raise ValueError("必须提供任务卡当前 revision")
    if not isinstance(changes, dict) or not changes:
        raise ValueError("没有提供要修改的字段")
    allowed = {"title", "notes", "status"}
    if set(changes) - allowed:
        raise ValueError("只允许修改标题、说明或状态")
    current = conn.execute(
        "SELECT id, title, notes, status, created_at, updated_at, revision "
        "FROM task_pool_tasks WHERE project_id=? AND id=?",
        (project_id, task_id),
    ).fetchone()
    if current is None:
        raise TaskNotFound("未找到该项目任务卡")
    current_dict = _task_dict(current)
    merged = {
        "title": changes.get("title", current_dict["title"]),
        "notes": changes.get("notes", current_dict["notes"]),
        "status": changes.get("status", current_dict["status"]),
    }
    normalized = _normalize_new_task(merged)
    now = _now()
    with conn:
        cursor = conn.execute(
            """UPDATE task_pool_tasks SET title=?, notes=?, status=?, updated_at=?, revision=revision+1
               WHERE project_id=? AND id=? AND revision=?""",
            (normalized["title"], normalized["notes"], normalized["status"], now,
             project_id, task_id, expected_revision),
        )
        if cursor.rowcount != 1:
            exists = conn.execute(
                "SELECT 1 FROM task_pool_tasks WHERE project_id=? AND id=?", (project_id, task_id)
            ).fetchone()
            if not exists:
                raise TaskNotFound("未找到该项目任务卡")
            raise RevisionConflict("任务卡已被修改；请重新读取后再提交，未覆盖其他修改")
        conn.execute(
            "UPDATE task_pool_boards SET revision=revision+1, updated_at=? WHERE project_id=?",
            (now, project_id),
        )
        row = conn.execute(
            "SELECT id, title, notes, status, created_at, updated_at, revision "
            "FROM task_pool_tasks WHERE project_id=? AND id=?",
            (project_id, task_id),
        ).fetchone()
        return {"task": _task_dict(row), "boardRevision": _board_revision(conn, project_id)}


def import_legacy(
    conn: sqlite3.Connection,
    project_id: str,
    source_key: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(source_key, str) or not source_key.strip() or len(source_key) > 300:
        raise ValueError("旧数据来源标识无效")
    if not isinstance(items, list) or len(items) > 10000:
        raise ValueError("旧任务数据格式异常，未覆盖原数据")
    normalized = [_normalize_legacy_task(item) for item in items]
    now = _now()
    with conn:
        prior = conn.execute(
            "SELECT result_json FROM task_pool_legacy_imports WHERE project_id=? AND source_key=?",
            (project_id, source_key),
        ).fetchone()
        if prior:
            return json.loads(prior[0])

        inserted = 0
        conflicts = 0
        for task in normalized:
            existing = conn.execute(
                "SELECT id, title, notes, status, created_at, updated_at, revision "
                "FROM task_pool_tasks WHERE project_id=? AND id=?",
                (project_id, task["id"]),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO task_pool_tasks
                       (project_id, id, title, notes, status, created_at, updated_at, revision)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (project_id, task["id"], task["title"], task["notes"], task["status"],
                     task["createdAt"], task["updatedAt"], task["revision"]),
                )
                inserted += 1
                continue
            current = _task_dict(existing)
            same = all(current[key] == task[key] for key in ("id", "title", "notes", "status", "createdAt", "updatedAt"))
            if not same:
                conn.execute(
                    """INSERT OR IGNORE INTO task_pool_legacy_conflicts
                       (project_id, task_id, source_key, payload_json, recorded_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (project_id, task["id"], source_key, _json(task), now),
                )
                conflicts += 1
        if inserted:
            conn.execute(
                "UPDATE task_pool_boards SET revision=revision+1, updated_at=? WHERE project_id=?",
                (now, project_id),
            )
        result = {"inserted": inserted, "conflicts": conflicts, "boardRevision": _board_revision(conn, project_id)}
        conn.execute(
            "INSERT INTO task_pool_legacy_imports(project_id, source_key, result_json, imported_at) "
            "VALUES (?, ?, ?, ?)",
            (project_id, source_key, _json(result), now),
        )
        return result


def _normalize_legacy_task(item: Any) -> dict[str, Any]:
    normalized = _normalize_new_task(item)
    task_id = item.get("id") if isinstance(item, dict) else None
    created_at = item.get("createdAt") if isinstance(item, dict) else None
    updated_at = item.get("updatedAt") if isinstance(item, dict) else None
    revision = item.get("revision", 1) if isinstance(item, dict) else 1
    if not isinstance(task_id, str) or not task_id.strip() or len(task_id) > 200:
        raise ValueError("旧任务数据格式异常，未覆盖原数据")
    if not isinstance(created_at, str) or not created_at or not isinstance(updated_at, str) or not updated_at:
        raise ValueError("旧任务时间格式异常，未覆盖原数据")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        revision = 1
    return {"id": task_id, **normalized, "createdAt": created_at, "updatedAt": updated_at, "revision": revision}


def _board_revision(conn: sqlite3.Connection, project_id: str) -> int:
    row = conn.execute(
        "SELECT revision FROM task_pool_boards WHERE project_id=?", (project_id,)
    ).fetchone()
    return 0 if row is None else row[0]


def count_legacy_conflicts(conn: sqlite3.Connection, project_id: str, task_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM task_pool_legacy_conflicts WHERE project_id=? AND task_id=?",
        (project_id, task_id),
    ).fetchone()[0]
