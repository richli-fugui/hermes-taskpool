import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from agent_plugin import tools
from agent_plugin import store


class FakeContext:
    def __init__(self, cwd):
        self.cwd = cwd
        self.tools = {}

    def session_cwd(self):
        return self.cwd

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs


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


class AgentToolTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        store.init_db(self.conn)
        self.project = SimpleNamespace(
            id="registered-a", name="项目 A", primary_path="C:/Work/A", archived=False
        )
        self.ctx = FakeContext("C:/Work/A/src")

        def resolve(_ctx):
            if self.ctx.cwd.startswith("C:/Work/A"):
                return self.project
            return None

        self.db = NoCloseConnection(self.conn)
        tools.register_tools(self.ctx, project_resolver=resolve, db_opener=lambda: self.db)

    def tearDown(self):
        self.conn.close()

    def test_task_card_intent_is_routed_to_task_pool_workflow(self):
        list_description = self.ctx.tools["task_pool_list"]["schema"]["description"]
        add_description = self.ctx.tools["task_pool_add"]["schema"]["description"]
        update_description = self.ctx.tools["task_pool_update"]["schema"]["description"]

        self.assertIn("整理一下任务卡", list_description)
        self.assertIn("Task Pool", list_description)
        self.assertIn("not Hermes Kanban or todo_list", list_description)
        self.assertIn("task_pool_list", add_description)
        self.assertIn("task_pool_list", update_description)
        self.assertIn("revision", update_description)

    def test_agent_tools_are_real_project_scoped_read_write_tools(self):
        self.assertEqual(
            set(self.ctx.tools), {"task_pool_list", "task_pool_add", "task_pool_update"}
        )
        added = self.ctx.tools["task_pool_add"]["handler"](
            {"tasks": [{"title": "Agent 写入", "notes": "共享卡池", "status": "blocked"}],
             "request_key": "agent-run-1"}
        )

        self.assertTrue(json.loads(added)["ok"], added)
        listed = self.ctx.tools["task_pool_list"]["handler"]({})
        self.assertIn("Agent 写入", listed)
        self.assertIn("registered-a", listed)
        self.assertEqual(len(store.read_board(self.conn, "registered-a")["tasks"]), 1)

    def test_unregistered_session_cwd_fails_closed_without_creating_board(self):
        self.ctx.cwd = "C:/Other/Project"
        result = self.ctx.tools["task_pool_add"]["handler"](
            {"tasks": [{"title": "不应写入"}]}
        )

        self.assertIn("项目身份未确认，拒绝写入", result)
        self.assertEqual(store.read_board(self.conn, "registered-a")["tasks"], [])

    def test_error_payloads_include_machine_code_and_repair_hint(self):
        self.ctx.cwd = "C:/Other/Project"
        result = json.loads(self.ctx.tools["task_pool_add"]["handler"](
            {"tasks": [{"title": "不应写入"}]}
        ))

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "PROJECT_IDENTITY_UNCONFIRMED")
        self.assertIn("Hermes Projects", result["hint"])

        self.ctx.cwd = "C:/Work/A/src"
        self.ctx.tools["task_pool_add"]["handler"]({"tasks": [{"title": "卡A"}]})
        task = store.read_board(self.conn, "registered-a")["tasks"][0]
        stale = json.loads(self.ctx.tools["task_pool_update"]["handler"](
            {"task_id": task["id"], "expected_revision": task["revision"] + 5, "status": "doing"}
        ))

        self.assertFalse(stale["ok"])
        self.assertEqual(stale["code"], "REVISION_CONFLICT")
        self.assertIn("task_pool_list", stale["hint"])

    def test_add_description_guides_minimal_card_decomposition(self):
        description = self.ctx.tools["task_pool_add"]["schema"]["description"]

        for marker in (
            "one completable step",
            "split it into separate cards",
            "acceptance criteria",
        ):
            self.assertIn(marker, description)

    def test_agent_update_uses_revision_guard(self):
        self.ctx.tools["task_pool_add"]["handler"](
            {"tasks": [{"title": "待更新"}], "request_key": "first"}
        )
        board = store.read_board(self.conn, "registered-a")
        task = board["tasks"][0]
        result = self.ctx.tools["task_pool_update"]["handler"](
            {"task_id": task["id"], "expected_revision": task["revision"],
             "status": "doing"}
        )

        self.assertTrue(json.loads(result)["ok"])
        self.assertEqual(store.read_board(self.conn, "registered-a")["tasks"][0]["status"], "doing")


if __name__ == "__main__":
    unittest.main()
