from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("work_completion", ROOT / "scripts" / "work_completion.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class WorkCompletionTests(unittest.TestCase):
    def path(self, temp: str) -> Path:
        return Path(temp) / "work-items.json"

    def register(self, path: Path):
        return mod.register(
            path,
            work_id="wi-1",
            project_id="agentmanager",
            title="ship feature",
            owner="role://completion.controller",
            next_action="implement code",
            acceptance=["tests pass", "production receipt exists"],
        )

    def test_active_work_requires_owner_next_action_and_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            item = self.register(path)
            self.assertEqual(item["status"], "accepted")
            errors, active = mod.audit(path)
            self.assertEqual(errors, [])
            self.assertEqual(active, ["wi-1"])

    def test_done_requires_verification_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            mod.transition(path, work_id="wi-1", target="in_progress", actor="agent", next_action="run test")
            mod.transition(path, work_id="wi-1", target="verifying", actor="agent", next_action="verify prod")
            with self.assertRaises(ValueError):
                mod.transition(path, work_id="wi-1", target="done", actor="agent", evidence=["run 1"])
            done = mod.transition(
                path, work_id="wi-1", target="done", actor="inspector",
                evidence=["https://example.invalid/receipt"], verification="passed",
            )
            self.assertEqual(done["status"], "done")
            self.assertEqual(done["verification"]["status"], "passed")

    def test_handoff_keeps_work_alive_and_advances_owner_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            moved = mod.handoff(
                path, work_id="wi-1", actor="chat-agent",
                new_owner="role://lobster", next_action="resume from PR 42",
            )
            self.assertEqual(moved["owner"], "role://lobster")
            self.assertEqual(moved["owner_generation"], 2)
            self.assertEqual(mod.next_item(path)["work_id"], "wi-1")

    def test_blocked_work_cannot_lose_blocker(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            with self.assertRaises(ValueError):
                mod.transition(path, work_id="wi-1", target="blocked", actor="agent", next_action="wait")
            blocked = mod.transition(
                path, work_id="wi-1", target="blocked", actor="agent",
                next_action="retry after credentials", blocker="credential unavailable",
            )
            self.assertEqual(blocked["status"], "blocked")

    def test_board_projection_survives_context_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            board = Path(temp) / "TASK_BOARD.md"
            board.write_text("# Existing Board\n\n## Other\n", encoding="utf-8")
            self.register(path)
            mod.project_board(path, board)
            first = board.read_text(encoding="utf-8")
            self.assertIn("[WI:wi-1] implement code", first)
            self.assertIn("Existing Board", first)
            mod.project_board(path, board)
            second = board.read_text(encoding="utf-8")
            self.assertEqual(second.count("<!-- WORK_COMPLETION_START -->"), 1)
            self.assertEqual(second.count("[WI:wi-1]"), 1)

    def test_work_item_can_pin_a_non_runtime_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            workspace = str(Path(temp) / "workspace")
            item = mod.register(
                path,
                work_id="wi-workspace",
                project_id="agentmanager",
                title="continue safely",
                owner="role://completion.controller",
                next_action="resume implementation",
                acceptance=["verified receipt"],
                workspace=workspace,
            )
            self.assertEqual(item["workspace"], workspace)

    def test_verified_done_helper_walks_required_states(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.path(temp)
            self.register(path)
            item = mod.verified_done(path, work_id="wi-1", actor="lobster+inspector", evidence="physical-output-pass")
            self.assertEqual(item["status"], "done")
            self.assertEqual(mod.audit(path), ([], []))


if __name__ == "__main__":
    unittest.main()
