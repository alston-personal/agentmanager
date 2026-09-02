from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import EmployeeWakePlanner
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


class EmployeeWakeInboxSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        runtime = EmployeeRuntime(self.root / "runtime")
        runtime.create_employee("steward", "Steward", role_ids=["governance.spec_steward"])
        runtime.create_assignment("audit-1", "steward", "Audit safely")
        intent = EmployeeWakePlanner(EmployeeLifecycle(runtime)).plan_next("steward")
        self.assertIsNotNone(intent)
        self.intent = intent.as_dict()
        self.client = ThinClient(
            NodeIdentity("realm-test", "node-a"),
            ThinClientPolicy(employee_wake_root=self.root / "wakes"),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _task(self, intent):
        return {
            "schema": "agentos.node-task/v0.1",
            "task_id": "wake-security",
            "action": "agent.employee.wake.deliver",
            "wake_intent": intent,
            "employee_wake_route": {
                "schema": "agentos.employee-wake-route/v1",
                "employee_id": "steward",
                "node_id": "node-a",
                "presence_id": "presence-a",
                "presence_generation": 1,
            },
        }

    def test_unexpected_secret_like_key_name_is_not_reflected_in_receipt(self):
        intent = dict(self.intent)
        marker = "DO_NOT_REFLECT_PRIVATE_MARKER_7f4b"
        intent[marker] = "value"
        receipt = self.client.execute(self._task(intent))
        self.assertFalse(receipt["ok"])
        self.assertNotIn(marker, receipt.get("error", ""))
        self.assertIn("unexpected_employee_wake_fields", receipt.get("error", ""))

    def test_secret_like_value_is_not_reflected_in_receipt(self):
        intent = dict(self.intent)
        marker = "bearer DO_NOT_REFLECT_PRIVATE_VALUE_91ab"
        intent["goal"] = marker
        receipt = self.client.execute(self._task(intent))
        self.assertFalse(receipt["ok"])
        self.assertNotIn(marker, receipt.get("error", ""))
        self.assertIn("employee_wake_secret_like_value", receipt.get("error", ""))


if __name__ == "__main__":
    unittest.main()
