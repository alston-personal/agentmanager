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


class ProviderQuotaRecoveryTests(unittest.TestCase):
    def setup_work(self, path: Path):
        return mod.register(
            path, work_id="wi-quota", project_id="agentmanager",
            title="continue after Gemini exhaustion",
            owner="executor://oracle-gemini",
            next_action="finish checked out files",
            acceptance=["tests", "receipt"],
        )

    def recover(self, path: Path, **overrides):
        params = dict(
            work_id="wi-quota", actor="role://completion.controller",
            failed_owner="executor://oracle-gemini",
            expected_generation=1,
            failure_receipt="oracle-receipt://quota-001",
            failure_reason="provider quota exhausted",
            next_action="reconcile Git HEAD, dirty worktree and unacknowledged tool calls",
        )
        params.update(overrides)
        return mod.recover_provider_failure(path, **params)

    def test_sudden_quota_exhaustion_fences_old_executor_without_its_ack(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "work-items.json"
            self.setup_work(path)
            mod.assert_execution_fence(
                path, work_id="wi-quota", owner="executor://oracle-gemini", generation=1,
            )
            recovered = self.recover(path)
            self.assertEqual(recovered["owner"], "role://completion.controller")
            self.assertEqual(recovered["owner_generation"], 2)
            self.assertEqual(recovered["status"], "blocked")
            self.assertEqual(recovered["blocker"], "provider_capacity_recovery_pending_reconciliation")
            self.assertIn("reconcile", recovered["next_action"])
            self.assertEqual(recovered["history"][-1]["failure_receipt"], "oracle-receipt://quota-001")
            with self.assertRaisesRegex(ValueError, "stale_generation"):
                mod.assert_execution_fence(
                    path, work_id="wi-quota", owner="executor://oracle-gemini", generation=1,
                )
            self.assertIsNone(mod.next_item(path))
            self.assertEqual(mod.audit(path)[0], [])

    def test_duplicate_or_late_recovery_cannot_steal_new_lease(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "work-items.json"
            self.setup_work(path)
            self.recover(path)
            with self.assertRaisesRegex(ValueError, "stale_generation"):
                self.recover(path)
            self.assertEqual(mod.load(path)["items"]["wi-quota"]["owner_generation"], 2)

    def test_recovery_requires_controller_capacity_receipt_and_valid_context(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "work-items.json"
            self.setup_work(path)
            for override, error in [
                ({"actor": "executor://other-model"}, "controller_required"),
                ({"failure_reason": "human approval required"}, "not_capacity_failure"),
                ({"failure_receipt": ""}, "required_fields"),
                ({"expected_generation": 0}, "generation_invalid"),
            ]:
                with self.subTest(override=override):
                    with self.assertRaisesRegex(ValueError, error):
                        self.recover(path, **override)
            self.assertEqual(mod.load(path)["items"]["wi-quota"]["owner_generation"], 1)

    def test_expired_or_mismatched_fence_blocks_new_side_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "work-items.json"
            self.setup_work(path)
            with self.assertRaisesRegex(ValueError, "stale_generation"):
                mod.assert_execution_fence(
                    path, work_id="wi-quota", owner="executor://oracle-gemini", generation=2,
                )
            state = mod.load(path)
            state["items"]["wi-quota"]["lease_expires_at"] = "2000-01-01T00:00:00+00:00"
            mod.save(path, state)
            with self.assertRaisesRegex(ValueError, "lease_expired"):
                mod.assert_execution_fence(
                    path, work_id="wi-quota", owner="executor://oracle-gemini", generation=1,
                )


if __name__ == "__main__":
    unittest.main()
