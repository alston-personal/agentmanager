from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.controller_service import ControllerService
from agent_core.core_supervisor_delivery import (
    SupervisorWakeAuthorityResolver,
    SupervisorWakeCoordinator,
)
from agent_core.core_supervisor_service import CoreSupervisorService
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import EmployeePresenceRegistry
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake_delivery import EmployeeWakeDelivery
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


T0 = datetime(2026, 9, 2, 6, 0, 0, tzinfo=timezone.utc)


class CoreSupervisorDeliveryTests(unittest.TestCase):
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
            "Audit closure gaps",
            thread_head="ir:start",
            constraints=["read-only-first"],
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)

        self.node_registry = NodeRegistry(path=self.root / "one" / "realm" / "nodes.json")
        self.fabric = RealmFabricStore(
            path=self.root / "one" / "realm" / "fabric.json",
            node_registry=self.node_registry,
        )
        self.fabric.initialize_realm("realm-test")
        self.wake_root = self.root / "node-wakes"
        self.client = ThinClient(
            NodeIdentity("realm-test", "node-a"),
            ThinClientPolicy(employee_wake_root=self.wake_root),
        )
        manifest = self.client.capability_manifest()
        invite = self.fabric.create_invite(expires_minutes=5, label="supervisor-s4-test")
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
        self.controller = ControllerService(self.fabric)
        self.wake_delivery = EmployeeWakeDelivery(self.presence, self.controller)

    def tearDown(self):
        self.tmp.cleanup()

    def _service(self, *, available_transports=None, bind_presence=True):
        if bind_presence:
            self.presence.bind(
                "spec-steward",
                "node-a",
                "presence-a",
                ttl_seconds=120,
                now=T0,
            )
        service = CoreSupervisorService(
            self.lifecycle,
            owner_id="supervisor-test",
            base_poll_seconds=2,
            max_poll_seconds=16,
        )
        authority = SupervisorWakeAuthorityResolver(requested_transport="one_direct")
        coordinator = SupervisorWakeCoordinator(
            service,
            self.wake_delivery,
            authority,
            available_transports=available_transports or {"one_direct": True},
        )
        service.attach_delivery_driver(coordinator)
        return service, coordinator

    def _execute_all(self):
        tasks = self.fabric.pull_tasks("node-a", self.node_token, limit=10)
        receipts = []
        for task in tasks:
            receipt = self.client.execute(task)
            self.fabric.record_receipt(receipt, self.node_token)
            receipts.append(receipt)
        return tasks, receipts

    def _only_reconcile_id(self, service):
        files = list(service.intents_dir.glob("reconcile_*.json"))
        self.assertEqual(len(files), 1)
        return files[0].stem

    def test_cycle_progresses_plan_queue_receipt_and_real_assignment_claim(self):
        service, coordinator = self._service()
        leader = service.claim_leader(lease_seconds=60, now=T0)

        first = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self.assertEqual(first.new_intent_count, 1)
        self.assertTrue(first.dispatch_performed)
        self.assertEqual(first.delivery_dispatch_count, 1)
        self.assertEqual(first.delivery_queued_count, 1)
        self.assertEqual(first.authority_boundary, "persistent_observe_plan_plus_governed_wake_delivery")
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "pending")
        self.assertIsNone(self.lifecycle.get_lease("audit-001"))

        tasks, receipts = self._execute_all()
        self.assertEqual(len(tasks), 1)
        self.assertTrue(receipts[0]["wake_delivery"]["accepted"])
        self.assertFalse(receipts[0]["wake_delivery"]["executor_invoked"])

        second = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=2))
        self.assertFalse(second.dispatch_performed)
        self.assertEqual(second.delivery_awaiting_claim_count, 1)
        reconcile_id = self._only_reconcile_id(service)
        self.assertEqual(coordinator.get(reconcile_id).status, "awaiting_claim")

        lease = self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "executor-lease-1",
            lease_seconds=60,
            now=T0 + timedelta(seconds=3),
        )
        self.assertEqual(lease.generation, 1)
        third = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=4))
        self.assertEqual(third.delivery_claimed_count, 1)
        self.assertEqual(coordinator.get(reconcile_id).status, "claimed")

    def test_stale_exact_wake_is_superseded_without_delivery(self):
        service = CoreSupervisorService(
            self.lifecycle,
            owner_id="supervisor-test",
            base_poll_seconds=2,
            max_poll_seconds=16,
        )
        leader = service.claim_leader(lease_seconds=60, now=T0)
        planned = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self.assertEqual(planned.new_intent_count, 1)

        self.runtime.update_assignment("audit-001", thread_head="ir:changed-after-plan")
        authority = SupervisorWakeAuthorityResolver(requested_transport="one_direct")
        coordinator = SupervisorWakeCoordinator(
            service,
            self.wake_delivery,
            authority,
            available_transports={"one_direct": True},
        )
        service.attach_delivery_driver(coordinator)
        receipt = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=2))
        self.assertFalse(receipt.dispatch_performed)
        self.assertEqual(receipt.delivery_superseded_count, 1)
        self.assertEqual(self.fabric.load()["tasks"]["node-a"], [])

    def test_missing_presence_blocks_then_retries_when_presence_appears(self):
        service, coordinator = self._service(bind_presence=False)
        leader = service.claim_leader(lease_seconds=60, now=T0)
        first = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self.assertFalse(first.dispatch_performed)
        self.assertEqual(first.delivery_blocked_count, 1)
        reconcile_id = self._only_reconcile_id(service)
        self.assertEqual(coordinator.get(reconcile_id).error_code, "employee_presence_unavailable")

        self.presence.bind(
            "spec-steward",
            "node-a",
            "presence-a",
            ttl_seconds=120,
            now=T0 + timedelta(seconds=2),
        )
        second = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=3))
        self.assertTrue(second.dispatch_performed)
        self.assertEqual(second.delivery_queued_count, 1)
        self.assertEqual(len(self.fabric.load()["tasks"]["node-a"]), 1)

    def test_actions_availability_never_expands_control_plane_authority(self):
        service, coordinator = self._service(available_transports={"github_actions": True})
        leader = service.claim_leader(lease_seconds=60, now=T0)
        receipt = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self.assertFalse(receipt.dispatch_performed)
        self.assertEqual(receipt.delivery_blocked_count, 1)
        reconcile_id = self._only_reconcile_id(service)
        state = coordinator.get(reconcile_id)
        self.assertEqual(state.status, "blocked")
        self.assertEqual(state.error_code, "wake_authority_unavailable")
        self.assertEqual(self.fabric.load()["tasks"]["node-a"], [])

    def test_awaiting_claim_is_not_resent_to_same_presence(self):
        service, coordinator = self._service()
        leader = service.claim_leader(lease_seconds=60, now=T0)
        service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self._execute_all()
        service.run_cycle(leader.generation, now=T0 + timedelta(seconds=2))
        reconcile_id = self._only_reconcile_id(service)
        self.assertEqual(coordinator.get(reconcile_id).status, "awaiting_claim")

        third = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=3))
        self.assertFalse(third.dispatch_performed)
        self.assertEqual(self.fabric.pull_tasks("node-a", self.node_token, limit=10), [])
        self.assertEqual(coordinator.get(reconcile_id).status, "awaiting_claim")

    def test_unclaimed_wake_can_follow_new_presence_generation(self):
        service, coordinator = self._service()
        leader = service.claim_leader(lease_seconds=60, now=T0)
        service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self._execute_all()
        service.run_cycle(leader.generation, now=T0 + timedelta(seconds=2))
        reconcile_id = self._only_reconcile_id(service)
        self.assertEqual(coordinator.get(reconcile_id).status, "awaiting_claim")

        second_presence = self.presence.bind(
            "spec-steward",
            "node-a",
            "presence-b",
            ttl_seconds=120,
            supersede_presence_id="presence-a",
            now=T0 + timedelta(seconds=3),
        )
        self.assertEqual(second_presence.generation, 2)
        fourth = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=4))
        self.assertTrue(fourth.dispatch_performed)
        state = coordinator.get(reconcile_id)
        self.assertEqual(state.status, "queued")
        self.assertEqual(state.presence_generation, 2)
        tasks = self.fabric.pull_tasks("node-a", self.node_token, limit=10)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["employee_wake_route"]["presence_generation"], 2)


if __name__ == "__main__":
    unittest.main()
