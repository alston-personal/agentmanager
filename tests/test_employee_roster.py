from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_roster import inspect_employee_roster
from agent_core.employee_runtime import EmployeeRuntime


T0 = datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc)


class EmployeeRosterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.runtime.create_employee("zeus-writer", "Zeus Writer", role_ids=["product.zeus_writer"])
        self.runtime.create_assignment("chapter-work", "zeus-writer", "private goal text")

    def view(self, *, now=T0, expected=("zeus-writer", "youtube-ai-manager", "mio")):
        data = inspect_employee_roster(self.root, now=now, expected_employee_ids=expected)
        return data, {x["employee_id"]: x for x in data["roles"]}

    def test_missing_role_and_pending_have_no_false_green(self):
        data, roles = self.view()
        self.assertEqual(data["schema"], "agentos.employee-roster/v1")
        self.assertFalse(data["mutation_allowed"])
        self.assertFalse(data["role_health_verified"])
        self.assertIsNone(data["supervisor_service_live"])
        self.assertEqual(roles["mio"]["registration"], "not_registered")
        self.assertEqual(roles["youtube-ai-manager"]["registration"], "not_registered")
        self.assertEqual(roles["zeus-writer"]["state"], "pending")
        self.assertFalse(roles["zeus-writer"]["autonomous_liveness_verified"])
        self.assertEqual(roles["zeus-writer"]["assignments"][0]["next_due_at"], None)
        self.assertNotIn("private goal text", json.dumps(data))

    def test_valid_lease_is_running_not_product_success_or_autonomy(self):
        self.lifecycle.claim("chapter-work", "zeus-writer", "lease-a", lease_seconds=60, now=T0)
        data, roles = self.view(now=T0 + timedelta(seconds=5))
        role = roles["zeus-writer"]
        self.assertEqual(role["state"], "running")
        self.assertFalse(role["autonomous_liveness_verified"])
        self.assertFalse(role["assignments"][0]["product_work_verified"])
        self.assertIsNone(role["assignments"][0]["executor_available"])
        self.assertNotIn("lease-a", json.dumps(data))

    def test_expired_lease_is_unknown_not_healthy_or_safely_retriable(self):
        self.lifecycle.claim("chapter-work", "zeus-writer", "lease-a", lease_seconds=60, now=T0)
        _, roles = self.view(now=T0 + timedelta(seconds=61))
        assignment = roles["zeus-writer"]["assignments"][0]
        self.assertEqual(assignment["state"], "unknown")
        self.assertEqual(assignment["blocker_code"], "expired_lease_prior_execution_unknown")
        self.assertEqual(roles["zeus-writer"]["blocker_code"], "assignment_evidence_incomplete")

    def test_terminal_without_matching_receipt_fails_closed(self):
        self.runtime.update_assignment("chapter-work", state="completed")
        _, roles = self.view()
        assignment = roles["zeus-writer"]["assignments"][0]
        self.assertEqual(assignment["state"], "unknown")
        self.assertEqual(assignment["blocker_code"], "terminal_receipt_missing_or_mismatch")

    def test_valid_terminal_receipt_is_evidence_not_fresh_activity(self):
        self.lifecycle.claim("chapter-work", "zeus-writer", "lease-a", lease_seconds=60, now=T0)
        self.lifecycle.finish("chapter-work", "lease-a", state="completed", result_summary={"private": "never expose"}, now=T0 + timedelta(seconds=5))
        data, roles = self.view(now=T0 + timedelta(days=1))
        role = roles["zeus-writer"]
        self.assertEqual(role["state"], "idle")
        receipt = role["assignments"][0]["last_terminal_receipt"]
        self.assertEqual(receipt["outcome"], "completed")
        self.assertEqual(receipt["evidence_ref"], "employee-receipt:chapter-work:1")
        self.assertFalse(role["autonomous_liveness_verified"])
        self.assertNotIn("never expose", json.dumps(data))

    def test_corrupt_receipt_not_silently_accepted(self):
        self.lifecycle.claim("chapter-work", "zeus-writer", "lease-a", lease_seconds=60, now=T0)
        self.lifecycle.finish("chapter-work", "lease-a", now=T0 + timedelta(seconds=5))
        path = self.root / "lifecycle" / "receipts" / "chapter-work" / "000001.json"
        path.write_text('{"schema":"wrong"}', encoding="utf-8")
        _, roles = self.view()
        a = roles["zeus-writer"]["assignments"][0]
        self.assertEqual(a["state"], "unknown")
        self.assertEqual(a["blocker_code"], "canonical_lifecycle_evidence_invalid")
        self.assertIsNone(a["last_terminal_receipt"])

    def test_bad_runtime_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "runtime_root_must_be_absolute"):
            inspect_employee_roster("relative/path", expected_employee_ids=())


if __name__ == "__main__":
    unittest.main()
