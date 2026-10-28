import sqlite3
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from agent_plugin.dashboard import plugin_api


class NoCloseConnection:
    def __init__(self, conn):
        self.conn = conn

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def close(self):
        pass

    def __enter__(self):
        self.conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self.conn.__exit__(exc_type, exc, traceback)


class PluginApiTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        plugin_api.store.init_db(self.conn)
        self.db = NoCloseConnection(self.conn)
        self.project = SimpleNamespace(
            id="registered-a", name="项目 A", primary_path="C:/Work/A", archived=False,
            folders=[],
        )
        self.scope_patch = patch.object(
            plugin_api, "_resolve_project", return_value=(self.project, self.project.primary_path)
        )
        self.db_patch = patch.object(plugin_api.store, "open_db", return_value=self.db)
        self.scope_patch.start()
        self.db_patch.start()
        self.addCleanup(self.scope_patch.stop)
        self.addCleanup(self.db_patch.stop)

    def tearDown(self):
        self.conn.close()

    def test_desktop_api_and_agent_tools_use_the_same_board_store(self):
        added = plugin_api.add_task(
            "registered-a",
            plugin_api.AddBody(
                cwd="C:/Work/A",
                task=plugin_api.TaskInput(title="桌面创建", notes="API 写入", status="todo"),
                request_key="desktop-1",
            ),
        )
        listed = plugin_api.get_tasks("registered-a", "C:/Work/A")

        self.assertEqual(added["task"]["id"], listed["tasks"][0]["id"])
        self.assertEqual(listed["tasks"][0]["title"], "桌面创建")

    def test_desktop_update_uses_revision_and_rejects_stale_writer(self):
        added = plugin_api.add_task(
            "registered-a",
            plugin_api.AddBody(cwd="C:/Work/A", task=plugin_api.TaskInput(title="编辑目标")),
        )
        task = added["task"]
        body = plugin_api.UpdateBody(
            cwd="C:/Work/A", expected_revision=task["revision"], status="doing"
        )
        updated = plugin_api.update_task("registered-a", task["id"], body)
        stale = plugin_api.UpdateBody(
            cwd="C:/Work/A", expected_revision=task["revision"], status="done"
        )

        self.assertEqual(updated["task"]["status"], "doing")
        with self.assertRaises(plugin_api.HTTPException) as caught:
            plugin_api.update_task("registered-a", task["id"], stale)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(plugin_api.store.read_board(self.conn, "registered-a")["tasks"][0]["status"], "doing")

    def test_api_rejects_project_id_not_owned_by_the_supplied_cwd(self):
        self.scope_patch.stop()
        from hermes_cli import projects_db

        @contextmanager
        def connect_closing():
            yield object()

        with patch.object(projects_db, "connect_closing", connect_closing), patch.object(
            projects_db, "project_for_path", lambda _conn, _cwd: self.project
        ):
            accepted, _ = plugin_api._resolve_project("registered-a", "C:/Work/A/src")
            self.assertEqual(accepted.id, "registered-a")
            with self.assertRaises(plugin_api.HTTPException) as caught:
                plugin_api._resolve_project("another-project", "C:/Work/A/src")

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail, "项目身份未确认，拒绝写入")


if __name__ == "__main__":
    unittest.main()
