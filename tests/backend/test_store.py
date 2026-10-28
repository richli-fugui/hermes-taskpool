import importlib.util
import sqlite3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = ROOT / "src" / "agent_plugin" / "store.py"
SPEC = importlib.util.spec_from_file_location("task_pool_store_under_test", STORE_PATH)
store = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(store)


class TaskPoolStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        store.init_db(self.conn)
        store.ensure_board(self.conn, "project-a", "项目 A", "C:/Work/A")
        store.ensure_board(self.conn, "project-b", "项目 B", "C:/Work/B")

    def tearDown(self):
        self.conn.close()

    def test_agent_add_is_visible_to_ui_reader_and_projects_are_isolated(self):
        added = store.add_tasks(
            self.conn,
            "project-a",
            [{"title": "Agent 建立的卡", "notes": "由项目 Agent 创建", "status": "blocked"}],
            request_key="run-001",
        )

        board_a = store.read_board(self.conn, "project-a")
        board_b = store.read_board(self.conn, "project-b")
        self.assertEqual(board_a["tasks"], added["tasks"])
        self.assertEqual(board_a["tasks"][0]["title"], "Agent 建立的卡")
        self.assertEqual(board_b["tasks"], [])

    def test_idempotent_add_request_does_not_duplicate_cards(self):
        first = store.add_tasks(
            self.conn, "project-a", [{"title": "幂等卡"}], request_key="stable-request"
        )
        second = store.add_tasks(
            self.conn, "project-a", [{"title": "幂等卡"}], request_key="stable-request"
        )

        self.assertEqual(first, second)
        self.assertEqual(len(store.read_board(self.conn, "project-a")["tasks"]), 1)

    def test_update_requires_current_revision_and_preserves_winning_edit(self):
        added = store.add_tasks(self.conn, "project-a", [{"title": "原始标题"}])
        task = added["tasks"][0]
        updated = store.update_task(
            self.conn,
            "project-a",
            task["id"],
            {"title": "第一次修改"},
            expected_revision=task["revision"],
        )

        with self.assertRaises(store.RevisionConflict):
            store.update_task(
                self.conn,
                "project-a",
                task["id"],
                {"title": "过期修改"},
                expected_revision=task["revision"],
            )

        current = store.read_board(self.conn, "project-a")["tasks"][0]
        self.assertEqual(updated["task"]["title"], "第一次修改")
        self.assertEqual(current["title"], "第一次修改")
        self.assertEqual(current["revision"], 2)

    def test_legacy_import_is_idempotent_and_keeps_conflicting_copy(self):
        original = store.add_tasks(self.conn, "project-a", [{"title": "Windows 旧卡"}])["tasks"][0]
        imported = store.import_legacy(
            self.conn,
            "project-a",
            "mac-device-a",
            [dict(original, title="Mac 上的旧卡内容")],
        )
        repeated = store.import_legacy(
            self.conn,
            "project-a",
            "mac-device-a",
            [dict(original, title="Mac 上的旧卡内容")],
        )

        self.assertEqual(imported, repeated)
        self.assertEqual(imported["conflicts"], 1)
        self.assertEqual(
            store.read_board(self.conn, "project-a")["tasks"][0]["title"], "Windows 旧卡"
        )
        self.assertEqual(
            store.count_legacy_conflicts(self.conn, "project-a", original["id"]), 1
        )

    def test_invalid_card_batch_is_rejected_without_partial_write(self):
        with self.assertRaises(ValueError):
            store.add_tasks(
                self.conn,
                "project-a",
                [{"title": "有效卡"}, {"title": "", "status": "unknown"}],
            )

        self.assertEqual(store.read_board(self.conn, "project-a")["tasks"], [])


if __name__ == "__main__":
    unittest.main()
