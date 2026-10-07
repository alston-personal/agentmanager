import tempfile
import unittest
from pathlib import Path

from agent_core.work_bindings import WorkBindingStore


class TestWorkBindingStore(unittest.TestCase):
    def test_upsert_preserves_existing_scope_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkBindingStore(Path(tmp) / "bindings.json")
            store.upsert({
                "work_id": "work-a",
                "project_id": "alpha",
                "node_id": "vopc5750",
                "executor_id": "codex-cli",
                "participant_id": "codex",
            })
            updated = store.upsert({"work_id": "work-a", "state": "suspended"})
            self.assertEqual(updated["project_id"], "alpha")
            self.assertEqual(updated["executor_id"], "codex-cli")
            self.assertEqual(updated["state"], "suspended")

    def test_terminal_binding_remains_available_as_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = WorkBindingStore(Path(tmp) / "bindings.json")
            store.upsert({"work_id": "work-a", "node_id": "oracle"})
            result = store.mark_terminal("work-a", state="completed", receipt_id="task-1")
            self.assertIsNotNone(result)
            self.assertEqual(result["state"], "completed")
            self.assertEqual(result["terminal_receipt_id"], "task-1")


if __name__ == "__main__":
    unittest.main()
