from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.controller_service import ControllerService
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import EmployeePresenceRegistry
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.employee_wake_delivery import NODE_RECEIPT_WAIT_SECONDS, EmployeeWakeDelivery
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


class EmployeeWakeReceiptTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 9, 11, 2, 0, 0, tzinfo=timezone.utc)
        self.runtime = EmployeeRuntime(self.root / "employee-runtime")
        self.runtime.create_employee(
            "worker",
            "Worker",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        self.runtime.create_assignment(
            "assignment-1",
            "worker",
            "Run bounded work",
            thread_head="ir:start",
            constraints=["read-only-first"],
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.planner = EmployeeWakePlanner(self.lifecycle)
        self.registry = NodeRegistry(self.root / "one" / "realm" / "nodes.json")
        self.fabric = RealmFabricStore(
            self.root / "one" / "realm" / "fabric.json",
            node_registry=self.registry,
        )
        self.fabric.initialize_realm("realm-test")
        self.wake_root = self.root / "wakes"
        self.client = ThinClient(
            NodeIdentity("realm-test", "node-a"),
            ThinClientPolicy(employee_wake_root=self.wake_root),
        )
        manifest = self.client.capability_manifest()
        invite = self.fabric.create_invite(expires_minutes=5, label="receipt-timeout-test")
        enrolled = self.fabric.enroll(
            invite_id=invite["invite_id"],
            code=invite["code"],
            manifest=manifest,
        )
        self.node_token = enrolled["node_token"]
        self.fabric.record_heartbeat(
            {
                "schema": "agentos.node-heartbeat/v0.1",
                "realm_id": "realm-test",
                "node_id": "node-a",
                "status": "online",
                "observed_at": None,
                "uptime_seconds": 10,
                "surface_count": 0,
                "manifest": manifest,
            },
            self.node_token,
        )
        self.presence = EmployeePresenceRegistry(self.runtime, self.registry)
        self.presence.bind(
            "worker",
            "node-a",
            "presence-a",
            ttl_seconds=120,
            now=self.now,
        )
        self.delivery = EmployeeWakeDelivery(self.presence, ControllerService(self.fabric))
        self.intent = self.planner.plan_next("worker", now=self.now)
        self.assertIsNotNone(self.intent)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_receipt_wait_is_bounded_then_becomes_unknown(self) -> None:
        queued = self.delivery.deliver_intent(self.intent, now=self.now)
        self.assertEqual(queued.status, "queued")

        early = self.delivery.reconcile(
            self.intent.wake_id,
            queued.presence_generation,
            now=self.now + timedelta(seconds=NODE_RECEIPT_WAIT_SECONDS - 1),
        )
        self.assertEqual(early.status, "queued")
        self.assertIsNone(early.error_code)

        timed_out = self.delivery.reconcile(
            self.intent.wake_id,
            queued.presence_generation,
            now=self.now + timedelta(seconds=NODE_RECEIPT_WAIT_SECONDS),
        )
        self.assertEqual(timed_out.status, "unknown")
        self.assertEqual(timed_out.error_code, "node_receipt_timeout")
        self.assertIsNotNone(timed_out.completed_at)

    def test_receipt_timeout_never_replays_same_presence_generation(self) -> None:
        queued = self.delivery.deliver_intent(self.intent, now=self.now)
        task_id = queued.task_id
        before = list(self.fabric.load()["tasks"]["node-a"])
        self.assertEqual(len(before), 1)

        timed_out = self.delivery.reconcile(
            self.intent.wake_id,
            queued.presence_generation,
            now=self.now + timedelta(seconds=NODE_RECEIPT_WAIT_SECONDS + 1),
        )
        self.assertEqual(timed_out.status, "unknown")

        repeated = self.delivery.deliver_intent(
            self.intent,
            now=self.now + timedelta(seconds=NODE_RECEIPT_WAIT_SECONDS + 2),
        )
        self.assertEqual(repeated.status, "unknown")
        self.assertEqual(repeated.task_id, task_id)
        after = list(self.fabric.load()["tasks"]["node-a"])
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0]["task_id"], task_id)


if __name__ == "__main__":
    unittest.main()
