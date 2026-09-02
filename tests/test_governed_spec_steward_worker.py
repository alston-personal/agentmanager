from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.spec_steward_acceptance import EXPECTED_AUTHORITY_POLICY
from agent_core.spec_steward_bootstrap import ensure_spec_steward
from agentos_node.employee_wake_inbox import deliver_employee_wake
from agentos_node.governed_spec_steward_worker import GovernedSpecStewardWakeWorker
from agentos_node.spec_steward_worker import ASSIGNMENT_ID, EMPLOYEE_ID


T0 = datetime(2026, 9, 2, 7, 30, 0, tzinfo=timezone.utc)
NODE_ID = "node-o3"


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class GovernedSpecStewardWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.runtime_root = base / "canonical"
        self.wake_root = base / "wake"
        self.state_root = base / "state"
        self.runtime = EmployeeRuntime(self.runtime_root)
        ensure_spec_steward(self.runtime)
        self.lifecycle = EmployeeLifecycle(self.runtime)
        wake = EmployeeWakePlanner(self.lifecycle).plan_next(EMPLOYEE_ID, now=T0)
        self.assertIsNotNone(wake)
        self.wake = wake
        self.route = {
            "schema": "agentos.employee-wake-route/v1",
            "employee_id": EMPLOYEE_ID,
            "node_id": NODE_ID,
            "presence_id": "presence-o3-1",
            "presence_generation": 1,
        }
        deliver_employee_wake(
            {"wake_intent": wake.as_dict(), "employee_wake_route": self.route},
            self.wake_root,
            expected_node_id=NODE_ID,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _worker(self):
        return GovernedSpecStewardWakeWorker(
            runtime_root=self.runtime_root,
            wake_root=self.wake_root,
            worker_state_root=self.state_root,
            node_id=NODE_ID,
            process_instance_id="governed-process-a",
            lease_seconds=60,
        )

    def _record_delivery(
        self,
        reconcile_id: str,
        *,
        transport: str = "one_direct",
        authority_policy_id: str = EXPECTED_AUTHORITY_POLICY,
        status: str = "awaiting_claim",
    ) -> None:
        self.assertTrue(reconcile_id.startswith("reconcile_"))
        _write(
            self.runtime_root / "supervisor" / "intents" / f"{reconcile_id}.json",
            {
                "schema": INTENT_RECORD_SCHEMA,
                "reconcile_id": reconcile_id,
                "state": "planned",
                "planned_at": T0.isoformat(),
                "planned_by_cycle": 1,
                "intent": {
                    "schema": RECONCILE_INTENT_SCHEMA,
                    "reconcile_id": reconcile_id,
                    "kind": "employee_wake",
                    "employee_id": EMPLOYEE_ID,
                    "assignment_id": ASSIGNMENT_ID,
                    "reason": "assignment_pending",
                    "wake_intent": self.wake.as_dict(),
                    "authority_boundary": "observe_and_select_only",
                    "node_selection": "unbound",
                    "executor_selection": "unbound",
                    "transport_selection": "unbound",
                    "capability_authority": "unbound",
                    "credential_exposed": False,
                },
                "dispatch_performed": False,
            },
        )
        _write(
            self.runtime_root / "supervisor" / "deliveries" / f"{reconcile_id}.json",
            {
                "schema": DELIVERY_STATE_SCHEMA,
                "reconcile_id": reconcile_id,
                "employee_id": EMPLOYEE_ID,
                "assignment_id": ASSIGNMENT_ID,
                "wake_id": self.wake.wake_id,
                "status": status,
                "created_at": T0.isoformat(),
                "updated_at": T0.isoformat(),
                "authority_policy_id": authority_policy_id,
                "transport_policy_id": "transport-routing-v1",
                "transport": transport,
                "transport_authority": "core_policy",
                "capability": WAKE_CAPABILITY,
                "supervisor_leader_generation": 1,
                "dispatch_performed": True,
                "presence_id": self.route["presence_id"],
                "presence_generation": self.route["presence_generation"],
                "node_id": NODE_ID,
                "wake_attempt_id": f"attempt-{reconcile_id}",
                "task_id": f"task-{reconcile_id}",
                "error_code": None,
            },
        )

    def test_local_capsule_without_s4_delivery_never_claims(self):
        with self.assertRaisesRegex(PermissionError, "governed_delivery_missing"):
            self._worker().process_one(now=T0)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))
        self.assertEqual(self.runtime.get_assignment(ASSIGNMENT_ID).state, "pending")

    def test_merely_queued_delivery_cannot_authorize_local_capsule(self):
        self._record_delivery("reconcile_queued", status="queued")
        with self.assertRaisesRegex(PermissionError, "governed_delivery_missing"):
            self._worker().process_one(now=T0)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))
        self.assertEqual(self.runtime.get_assignment(ASSIGNMENT_ID).state, "pending")

    def test_actions_like_transport_cannot_authorize_worker(self):
        self._record_delivery("reconcile_actions", transport="github_actions")
        with self.assertRaisesRegex(PermissionError, "governed_delivery_missing"):
            self._worker().process_one(now=T0)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))

    def test_wrong_authority_policy_cannot_authorize_worker(self):
        self._record_delivery("reconcile_wrong_policy", authority_policy_id="unrelated-policy")
        with self.assertRaisesRegex(PermissionError, "governed_delivery_missing"):
            self._worker().process_one(now=T0)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))

    def test_exact_node_acknowledged_s4_delivery_allows_bounded_worker_claim(self):
        self._record_delivery("reconcile_exact", status="awaiting_claim")
        state = self._worker().process_one(now=T0)
        self.assertEqual(state.status, "checkpointed")
        self.assertEqual(state.lease_generation, 1)
        lease = self.lifecycle.get_lease(ASSIGNMENT_ID)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.generation, 1)

    def test_duplicate_authority_records_fail_ambiguous_instead_of_picking_one(self):
        self._record_delivery("reconcile_one")
        self._record_delivery("reconcile_two")
        with self.assertRaisesRegex(PermissionError, "governed_delivery_ambiguous"):
            self._worker().process_one(now=T0)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))

    def test_terminal_or_unknown_delivery_is_not_preclaim_authority(self):
        self._record_delivery("reconcile_unknown", status="unknown")
        with self.assertRaisesRegex(PermissionError, "governed_delivery_missing"):
            self._worker().process_one(now=T0)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))


if __name__ == "__main__":
    unittest.main()
