from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.controller_service import ControllerService
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import EmployeePresenceRegistry, WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.employee_wake_delivery import DELIVERY_SCHEMA, EmployeeWakeDelivery
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


class EmployeeWakeDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root / "employee-runtime")
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        self.runtime.create_assignment(
            "audit-001",
            "spec-steward",
            "Audit open closure gaps",
            thread_head="ir:start",
            constraints=["read-only-first"],
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.planner = EmployeeWakePlanner(self.lifecycle)

        self.node_registry = NodeRegistry(path=self.root / "nodes.json")
        self.fabric = RealmFabricStore(path=self.root / "fabric.json", node_registry=self.node_registry)
        self.fabric.initialize_realm("realm-test")
        self.wake_root = self.root / "node-wakes"
        self.client = ThinClient(
            NodeIdentity("realm-test", "node-a"),
            ThinClientPolicy(employee_wake_root=self.wake_root),
        )
        manifest = self.client.capability_manifest()
        invite = self.fabric.create_invite(expires_minutes=5, label="wake-delivery-test")
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

        self.presence = EmployeePresenceRegistry(self.runtime, self.node_registry)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.presence.bind(
            "spec-steward",
            "node-a",
            "presence-a",
            ttl_seconds=120,
            now=self.now,
        )
        self.controller = ControllerService(self.fabric)
        self.delivery = EmployeeWakeDelivery(self.presence, self.controller)

    def tearDown(self):
        self.tmp.cleanup()

    def _intent(self):
        intent = self.planner.plan_next("spec-steward", now=self.now)
        self.assertIsNotNone(intent)
        return intent

    def _execute_one_task(self):
        tasks = self.fabric.pull_tasks("node-a", self.node_token, limit=10)
        self.assertEqual(len(tasks), 1)
        receipt = self.client.execute(tasks[0])
        self.fabric.record_receipt(receipt, self.node_token)
        return tasks[0], receipt

    def test_full_one_queue_node_receipt_reconcile_path(self):
        intent = self._intent()
        queued = self.delivery.deliver_intent(intent, now=self.now)
        self.assertEqual(queued.schema, DELIVERY_SCHEMA)
        self.assertEqual(queued.status, "queued")
        self.assertEqual(queued.presence_generation, 1)
        self.assertTrue(queued.controller_entered)

        task, node_receipt = self._execute_one_task()
        self.assertEqual(task["action"], WAKE_CAPABILITY)
        self.assertTrue(node_receipt["ok"])
        self.assertTrue(node_receipt["wake_delivery"]["accepted"])
        self.assertFalse(node_receipt["wake_delivery"]["executor_invoked"])
        self.assertEqual(node_receipt["wake_delivery"]["presence_id"], "presence-a")
        self.assertEqual(node_receipt["wake_delivery"]["presence_generation"], 1)

        delivered = self.delivery.reconcile(intent.wake_id, 1, now=self.now + timedelta(seconds=1))
        self.assertEqual(delivered.status, "delivered")
        self.assertTrue(delivered.node_ok)
        self.assertTrue(delivered.node_wake_accepted)

        assignment = self.runtime.get_assignment("audit-001")
        self.assertEqual(assignment.state, "pending")
        self.assertIsNone(self.lifecycle.get_lease("audit-001"))

    def test_node_without_explicit_wake_root_does_not_advertise_or_accept(self):
        client = ThinClient(NodeIdentity("realm-test", "node-b"), ThinClientPolicy())
        self.assertNotIn(WAKE_CAPABILITY, client.capability_manifest()["capabilities"])
        intent = self._intent()
        receipt = client.execute(
            {
                "schema": "agentos.node-task/v0.1",
                "task_id": "wake-node-b",
                "action": WAKE_CAPABILITY,
                "wake_intent": intent.as_dict(),
                "employee_wake_route": {
                    "schema": "agentos.employee-wake-route/v1",
                    "employee_id": "spec-steward",
                    "node_id": "node-b",
                    "presence_id": "presence-b",
                    "presence_generation": 1,
                },
            }
        )
        self.assertFalse(receipt["ok"])
        self.assertNotIn("wake_delivery", receipt)

    def test_route_target_node_mismatch_fails_closed_without_capsule(self):
        intent = self._intent()
        receipt = self.client.execute(
            {
                "schema": "agentos.node-task/v0.1",
                "task_id": "bad-route",
                "action": WAKE_CAPABILITY,
                "wake_intent": intent.as_dict(),
                "employee_wake_route": {
                    "schema": "agentos.employee-wake-route/v1",
                    "employee_id": "spec-steward",
                    "node_id": "some-other-node",
                    "presence_id": "presence-a",
                    "presence_generation": 1,
                },
            }
        )
        self.assertFalse(receipt["ok"])
        self.assertEqual(list(self.wake_root.rglob("*.json")), [])

    def test_route_employee_mismatch_fails_closed(self):
        intent = self._intent()
        receipt = self.client.execute(
            {
                "schema": "agentos.node-task/v0.1",
                "task_id": "wrong-employee",
                "action": WAKE_CAPABILITY,
                "wake_intent": intent.as_dict(),
                "employee_wake_route": {
                    "schema": "agentos.employee-wake-route/v1",
                    "employee_id": "someone-else",
                    "node_id": "node-a",
                    "presence_id": "presence-a",
                    "presence_generation": 1,
                },
            }
        )
        self.assertFalse(receipt["ok"])
        self.assertEqual(list(self.wake_root.rglob("*.json")), [])

    def test_same_exact_intent_and_presence_is_idempotent(self):
        intent = self._intent()
        first = self.delivery.deliver_intent(intent, now=self.now)
        second = self.delivery.deliver_intent(intent, now=self.now + timedelta(seconds=1))
        self.assertEqual(first.task_id, second.task_id)
        self.assertEqual(second.status, "queued")
        tasks = self.fabric.load()["tasks"]["node-a"]
        self.assertEqual(len(tasks), 1)

    def test_new_presence_generation_can_receive_same_unclaimed_wake(self):
        intent = self._intent()
        first = self.delivery.deliver_intent(intent, now=self.now)
        self.assertEqual(first.presence_generation, 1)
        self._execute_one_task()
        self.delivery.reconcile(intent.wake_id, 1, now=self.now + timedelta(seconds=1))

        second_presence = self.presence.bind(
            "spec-steward",
            "node-a",
            "presence-b",
            ttl_seconds=120,
            supersede_presence_id="presence-a",
            now=self.now + timedelta(seconds=2),
        )
        self.assertEqual(second_presence.generation, 2)
        second = self.delivery.deliver_intent(intent, now=self.now + timedelta(seconds=3))
        self.assertEqual(second.presence_generation, 2)
        self.assertNotEqual(first.task_id, second.task_id)
        task, receipt = self._execute_one_task()
        self.assertEqual(task["employee_wake_route"]["presence_generation"], 2)
        self.assertEqual(receipt["wake_delivery"]["presence_generation"], 2)
        capsules = sorted(self.wake_root.rglob("*.json"))
        self.assertEqual(len(capsules), 2)

    def test_interrupted_dispatch_record_becomes_unknown_and_is_not_redispatched(self):
        intent = self._intent()
        path = self.delivery._path(intent.wake_id, 1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": DELIVERY_SCHEMA,
                    "attempt_id": "attempt-crashed",
                    "wake_id": intent.wake_id,
                    "employee_id": intent.employee_id,
                    "assignment_id": intent.assignment_id,
                    "presence_id": "presence-a",
                    "presence_generation": 1,
                    "node_id": "node-a",
                    "task_id": "task-crashed",
                    "status": "dispatching",
                    "attempted_at": self.now.isoformat(),
                    "updated_at": self.now.isoformat(),
                    "queued_at": None,
                    "completed_at": None,
                    "node_ok": None,
                    "node_wake_accepted": None,
                    "error_code": None,
                    "controller_entered": None,
                    "credential_exposed": False,
                }
            ),
            encoding="utf-8",
        )
        state = self.delivery.deliver_intent(intent, now=self.now + timedelta(seconds=1))
        self.assertEqual(state.status, "unknown")
        self.assertEqual(state.error_code, "dispatch_interrupted_after_claim")
        self.assertEqual(self.fabric.load()["tasks"]["node-a"], [])

    def test_receipt_route_mismatch_is_not_accepted_as_delivery(self):
        intent = self._intent()
        queued = self.delivery.deliver_intent(intent, now=self.now)
        task = self.fabric.pull_tasks("node-a", self.node_token, limit=10)[0]
        receipt = self.client.execute(task)
        self.assertTrue(receipt["ok"])
        receipt["wake_delivery"]["presence_generation"] = 999
        self.fabric.record_receipt(receipt, self.node_token)
        state = self.delivery.reconcile(intent.wake_id, queued.presence_generation)
        self.assertEqual(state.status, "failed")
        self.assertFalse(state.node_wake_accepted)

    def test_missing_one_state_fails_before_dispatch_and_creates_no_shadow_store(self):
        intent = self._intent()
        missing_root = self.root / "missing-one"
        registry = NodeRegistry(path=missing_root / "realm" / "nodes.json")
        fabric = RealmFabricStore(path=missing_root / "realm" / "fabric.json", node_registry=registry)
        presence = EmployeePresenceRegistry(self.runtime, registry)
        delivery = EmployeeWakeDelivery(presence, ControllerService(fabric))
        with self.assertRaisesRegex(RuntimeError, "one_control_plane_state_missing"):
            delivery.deliver_intent(intent, now=self.now)
        self.assertFalse(fabric.path.exists())
        self.assertFalse(registry.path.exists())
        self.assertEqual(list(delivery.root.rglob("*.json")), [])

    def test_mismatched_one_realm_fails_before_dispatch(self):
        intent = self._intent()
        self.node_registry.path.write_text(
            json.dumps({"schema": "agentos.node-registry/v0.1", "realm_id": "other-realm", "nodes": {}}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "one_control_plane_realm_mismatch"):
            self.delivery.deliver_intent(intent, now=self.now)
        self.assertEqual(self.fabric.load()["tasks"].get("node-a", []), [])

    def test_presence_expiry_and_capability_freshness_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "employee_presence_expired"):
            self.presence.resolve("spec-steward", now=self.now + timedelta(seconds=121))


if __name__ == "__main__":
    unittest.main()
