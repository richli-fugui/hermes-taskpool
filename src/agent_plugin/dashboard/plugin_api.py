"""REST endpoints used by the pp-pane desktop UI; Agent tools call the same store directly."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter()
_STORE_MODULE = "_hermes_task_pool_store_pp_pane"


def _load_store():
    loaded = sys.modules.get(_STORE_MODULE)
    if loaded is not None:
        return loaded
    path = Path(__file__).resolve().parents[1] / "store.py"
    spec = importlib.util.spec_from_file_location(_STORE_MODULE, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("任务池存储模块不可用")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_STORE_MODULE] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_STORE_MODULE, None)
        raise
    return module


store = _load_store()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskInput(StrictModel):
    title: str = Field(min_length=1, max_length=store.MAX_TITLE_LENGTH)
    notes: str = Field(default="", max_length=store.MAX_NOTES_LENGTH)
    status: Literal["todo", "doing", "blocked", "review", "done"] = "todo"


class AddBody(StrictModel):
    cwd: str = Field(min_length=1)
    task: TaskInput
    request_key: str | None = Field(default=None, max_length=200)


class UpdateBody(StrictModel):
    cwd: str = Field(min_length=1)
    expected_revision: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=store.MAX_TITLE_LENGTH)
    notes: str | None = Field(default=None, max_length=store.MAX_NOTES_LENGTH)
    status: Literal["todo", "doing", "blocked", "review", "done"] | None = None


class LegacyImportBody(StrictModel):
    cwd: str = Field(min_length=1)
    source_key: str = Field(min_length=1, max_length=300)
    tasks: list[dict[str, Any]] = Field(max_length=10000)


def _resolve_project(project_id: str, cwd: str):
    if not project_id.strip() or not cwd.strip():
        raise HTTPException(status_code=403, detail="项目身份未确认，拒绝写入")
    from hermes_cli import projects_db

    try:
        with projects_db.connect_closing() as conn:
            project = projects_db.project_for_path(conn, cwd)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="无法验证 Hermes 项目身份") from exc
    if project is None or project.archived or project.id != project_id:
        raise HTTPException(status_code=403, detail="项目身份未确认，拒绝写入")
    path = project.primary_path or next(
        (folder.path for folder in project.folders if folder.is_primary), None
    )
    if not path:
        raise HTTPException(status_code=403, detail="项目身份未确认，拒绝写入")
    return project, path


def _ensure_board(conn, project, path: str) -> None:
    store.ensure_board(conn, project.id, project.name, path)


def _raise_store_error(exc: Exception):
    if isinstance(exc, store.RevisionConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, store.TaskNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, store.IdempotencyConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="任务池存储失败，数据未确认写入") from exc


@router.get("/projects/{project_id}/tasks")
def get_tasks(project_id: str, cwd: str):
    project, path = _resolve_project(project_id, cwd)
    conn = store.open_db()
    try:
        _ensure_board(conn, project, path)
        return store.read_board(conn, project_id)
    except Exception as exc:
        _raise_store_error(exc)
    finally:
        conn.close()


@router.post("/projects/{project_id}/tasks")
def add_task(project_id: str, body: AddBody):
    project, path = _resolve_project(project_id, body.cwd)
    conn = store.open_db()
    try:
        _ensure_board(conn, project, path)
        result = store.add_tasks(
            conn,
            project_id,
            [body.task.model_dump()],
            request_key=body.request_key,
        )
        return {"task": result["tasks"][0], "boardRevision": result["boardRevision"]}
    except Exception as exc:
        _raise_store_error(exc)
    finally:
        conn.close()


@router.patch("/projects/{project_id}/tasks/{task_id}")
def update_task(project_id: str, task_id: str, body: UpdateBody):
    project, path = _resolve_project(project_id, body.cwd)
    changes = {
        key: getattr(body, key)
        for key in ("title", "notes", "status")
        if key in body.model_fields_set
    }
    if not changes:
        raise HTTPException(status_code=422, detail="没有提供要修改的字段")
    conn = store.open_db()
    try:
        _ensure_board(conn, project, path)
        return store.update_task(
            conn,
            project_id,
            task_id,
            changes,
            expected_revision=body.expected_revision,
        )
    except Exception as exc:
        _raise_store_error(exc)
    finally:
        conn.close()


@router.post("/projects/{project_id}/legacy-import")
def import_legacy(project_id: str, body: LegacyImportBody):
    project, path = _resolve_project(project_id, body.cwd)
    conn = store.open_db()
    try:
        _ensure_board(conn, project, path)
        return store.import_legacy(conn, project_id, body.source_key, body.tasks)
    except Exception as exc:
        _raise_store_error(exc)
    finally:
        conn.close()
