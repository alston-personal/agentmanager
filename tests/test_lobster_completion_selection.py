from __future__ import annotations

import importlib.util
import inspect
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Keep this unit test focused on completion selection/ownership; Lobster's
# optional runtime integrations are not under test here.
if "yaml" not in sys.modules:
    yaml_stub = types.ModuleType("yaml")
    yaml_stub.safe_load = lambda *_args, **_kwargs: {}
    sys.modules["yaml"] = yaml_stub
if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    sys.modules["requests"] = requests_stub

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lobster_under_test", ROOT / "scripts" / "lobster.py")
lobster = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lobster)

work_completion = lobster.WorkCompletion


class LobsterCompletionSelectionTests(unittest.TestCase):
    def state_path(self, td: str) -> Path:
        return Path(td) / "work-items.json"

    def register(self, path: Path, work_id: str, project: str, status: str = "accepted"):
        item = work_completion.register(
            path,
            work_id=work_id,
            project_id=project,
            title=work_id,
            owner="role://completion.controller",
            next_action=f"finish {work_id}",
            acceptance=["verified"],
        )
        if status == "in_progress":
            item = work_completion.transition(
                path,
                work_id=work_id,
                target="in_progress",
                actor="role://completion.controller",
                next_action=f"finish {work_id}",
            )
        return item

    def test_selection_comes_from_ledger_not_project_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.state_path(td)
            self.register(path, "older-work", "z-project")
            self.register(path, "newer-work", "a-project")
            with patch.object(lobster, "COMPLETION_STATE", path):
                project, task = lobster.next_durable_completion_task()
            self.assertEqual(project, "z-project")
            self.assertEqual(task["work_id"], "older-work")
            self.assertEqual(task["source"], "completion-ledger")

    def test_in_progress_has_priority_over_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.state_path(td)
            self.register(path, "accepted-work", "a-project")
            self.register(path, "running-work", "z-project", status="in_progress")
            with patch.object(lobster, "COMPLETION_STATE", path):
                project, task = lobster.next_durable_completion_task()
            self.assertEqual(project, "z-project")
            self.assertEqual(task["work_id"], "running-work")

    def test_completion_begin_transitions_and_handoffs_to_lobster(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.state_path(td)
            self.register(path, "wi-claim", "market-master-evolution")
            with patch.object(lobster, "COMPLETION_STATE", path):
                work_id = lobster.completion_begin("[WI:wi-claim] finish wi-claim")
            self.assertEqual(work_id, "wi-claim")
            item = work_completion.load(path)["items"]["wi-claim"]
            self.assertEqual(item["status"], "in_progress")
            self.assertEqual(item["owner"], "role://lobster")
            self.assertTrue(any(h.get("event") == "handoff" for h in item["history"]))

    def test_task_wrapper_uses_resolved_role_name(self) -> None:
        source = inspect.getsource(lobster.run_claude_task_wrapper)
        self.assertIn("{role_name}", source)
        self.assertNotIn("{role}", source)

    def test_non_execution_owner_is_not_claimed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = self.state_path(td)
            work_completion.register(
                path,
                work_id="chat-owned",
                project_id="x",
                title="chat-owned",
                owner="role://chat-session",
                next_action="continue elsewhere",
                acceptance=["verified"],
            )
            with patch.object(lobster, "COMPLETION_STATE", path):
                self.assertIsNone(lobster.next_durable_completion_task())


if __name__ == "__main__":
    unittest.main()
