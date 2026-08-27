from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "continuation_state", ROOT / "scripts" / "continuation_state.py"
)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)

ContinuationState = mod.ContinuationState
UserEvent = mod.UserEvent
reconcile = mod.reconcile


class ContinuationStateTests(unittest.TestCase):
    def snapshot(self):
        return ContinuationState(
            snapshot_revision=7,
            snapshot_cutoff_seq=100,
            active_goal_revision=3,
            active_goal_text="Goal A: validate core parser",
            pending_user_events=[],
            unresolved_items=["publish web demo"],
        )

    def test_newer_goal_survives_old_tool_result(self):
        state = reconcile(
            self.snapshot(),
            [
                UserEvent(101, "goal", "Goal B: publish a usable web demo", 4),
                UserEvent(102, "tool_result", "Goal A validation passed"),
            ],
        )
        self.assertEqual(state.active_goal_revision, 4)
        self.assertEqual(state.active_goal_text, "Goal B: publish a usable web demo")

    def test_newer_correction_wins(self):
        state = reconcile(
            self.snapshot(),
            [
                UserEvent(101, "goal", "Goal B: publish a usable web demo", 4),
                UserEvent(102, "tool_result", "Goal A validation passed"),
                UserEvent(
                    103,
                    "correction",
                    "Goal B must be reachable from the official website",
                    5,
                ),
            ],
        )
        self.assertEqual(state.active_goal_revision, 5)
        self.assertEqual(
            state.active_goal_text,
            "Goal B must be reachable from the official website",
        )
        self.assertEqual(
            [event["seq"] for event in state.pending_user_events],
            [101, 102, 103],
        )

    def test_stale_revision_is_rejected(self):
        with self.assertRaises(ValueError):
            reconcile(
                self.snapshot(),
                [UserEvent(101, "goal", "stale goal", 2)],
            )

    def test_pre_cutoff_events_are_not_replayed(self):
        state = reconcile(
            self.snapshot(),
            [
                UserEvent(99, "goal", "ancient goal", 99),
                UserEvent(101, "goal", "current goal", 4),
            ],
        )
        self.assertEqual(state.active_goal_revision, 4)
        self.assertEqual(state.active_goal_text, "current goal")
        self.assertEqual([e["seq"] for e in state.pending_user_events], [101])


if __name__ == "__main__":
    unittest.main()
