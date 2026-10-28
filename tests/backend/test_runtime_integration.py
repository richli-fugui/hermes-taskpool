import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


class FakeAgentContext:
    def __init__(self, cwd):
        self.cwd = cwd
        self.tools = {}

    def session_cwd(self):
        return self.cwd

    def register_tool(self, **spec):
        self.tools[spec["name"]] = spec["handler"]


def load_package(name, folder):
    spec = importlib.util.spec_from_file_location(
        name,
        folder / "__init__.py",
        submodule_search_locations=[str(folder)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeIntegrationTests(unittest.TestCase):
    def test_agent_tools_and_desktop_http_routes_share_profile_db(self):
        from hermes_cli import projects_db
        from hermes_constants import reset_hermes_home_override, set_hermes_home_override

        scratch = Path(os.environ.get("TMPDIR") or (Path.home() / ".hermes" / "cache" / "scratch"))
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="task-pool-runtime-", dir=scratch) as tmp:
            root = Path(tmp)
            home = root / "hermes-home"
            project_path = root / "sample-project"
            home.mkdir()
            project_path.mkdir()
            token = set_hermes_home_override(home)
            package_name = "_pp_pane_runtime_test"
            try:
                with projects_db.connect_closing() as conn:
                    project_id = projects_db.create_project(
                        conn, name="Runtime integration project", primary_path=str(project_path)
                    )

                plugin = load_package(package_name, ROOT / "src" / "agent_plugin")
                ctx = FakeAgentContext(str(project_path))
                plugin.register(ctx)
                app = FastAPI()
                api_spec = importlib.util.spec_from_file_location(
                    "_pp_pane_runtime_test_api",
                    ROOT / "src" / "agent_plugin" / "dashboard" / "plugin_api.py",
                )
                api = importlib.util.module_from_spec(api_spec)
                sys.modules[api_spec.name] = api
                api_spec.loader.exec_module(api)
                app.include_router(api.router)

                listed = json.loads(ctx.tools["task_pool_list"]({}))
                self.assertTrue(listed["ok"])
                self.assertEqual(listed["tasks"], [])

                created_by_agent = json.loads(
                    ctx.tools["task_pool_add"](
                        {
                            "tasks": [{"title": "Agent card", "notes": "created by tool"}],
                            "request_key": "runtime-agent-add",
                        }
                    )
                )
                self.assertTrue(created_by_agent["ok"])

                with TestClient(app) as client:
                    response = client.get(
                        f"/projects/{project_id}/tasks", params={"cwd": str(project_path)}
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["tasks"][0]["title"], "Agent card")

                    created_by_ui = client.post(
                        f"/projects/{project_id}/tasks",
                        json={
                            "cwd": str(project_path),
                            "task": {"title": "Desktop card", "status": "todo"},
                            "request_key": "runtime-ui-add",
                        },
                    )
                    self.assertEqual(created_by_ui.status_code, 200, created_by_ui.text)
                    ui_task = created_by_ui.json()["task"]

                    updated_by_agent = json.loads(
                        ctx.tools["task_pool_update"](
                            {
                                "task_id": ui_task["id"],
                                "expected_revision": ui_task["revision"],
                                "status": "doing",
                            }
                        )
                    )
                    self.assertTrue(updated_by_agent["ok"])

                    response = client.get(
                        f"/projects/{project_id}/tasks", params={"cwd": str(project_path)}
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    tasks = {task["title"]: task for task in response.json()["tasks"]}
                    self.assertEqual(set(tasks), {"Agent card", "Desktop card"})
                    self.assertEqual(tasks["Desktop card"]["status"], "doing")

                    rejected = client.get(
                        "/projects/unrelated-project/tasks", params={"cwd": str(project_path)}
                    )
                    self.assertEqual(rejected.status_code, 403)
                    self.assertEqual(
                        rejected.json()["detail"], "项目身份未确认，拒绝写入"
                    )
            finally:
                reset_hermes_home_override(token)
                sys.modules.pop(package_name, None)
                sys.modules.pop(package_name + ".store", None)
                sys.modules.pop(package_name + ".tools", None)
                sys.modules.pop("_pp_pane_runtime_test_api", None)
                sys.modules.pop("_hermes_task_pool_store_pp_pane", None)


if __name__ == "__main__":
    unittest.main()
