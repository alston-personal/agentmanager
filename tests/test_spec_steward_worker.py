from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.core_supervisor import RECONCILE_INTENT_SCHEMA
from agent_core.core_supervisor_delivery import DELIVERY_STATE_SCHEMA
from agent_core.core_supervisor_service import INTENT_RECORD_SCHEMA
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.spec_steward_acceptance import (
    EXPECTED_AUTHORITY_POLICY,
    inspect_spec_steward_acceptance,
)
from agent_core.spec_steward_bootstrap import ensure_spec_steward
from agentos_node.employee_wake_inbox import deliver_employee_wake
from agentos_node.spec_steward_worker import (
    ASSIGNMENT_ID,
    EMPLOYEE_ID,
    WORKER_STATE_SCHEMA,
    SpecStewardWakeWorker,
)


T0 = datetime(2026, 9, 2, 7, 0, 0, tzinfo=timezone.utc)
NODE_ID = "node-o3"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SpecStewardWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.runtime_root = base / "canonical-employee-runtime"
        self.wake_root = base / "node-wake-inbox"
        self.state_root = base / "node-worker-state"
        self.runtime = EmployeeRuntime(self.runtime_root)
        ensure_spec_steward(self.runtime)
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.planner = EmployeeWakePlanner(self.lifecycle)

    def tearDown(self):
        self.tmp.cleanup()

    def _deliver_current_wake(self, *, now: datetime, presence_generation: int):
        wake = self.planner.plan_next(EMPLOYEE_ID, now=now)
        self.assertIsNotNone(wake)
        route = {
            "schema": "agentos.employee-wake-route/v1",
            "employee_id": EMPLOYEE_ID,
            "node_id": NODE_ID,
            "presence_id": f"presence-o3-{presence_generation}",
            "presence_generation": presence_generation,
        }
        result = deliver_employee_wake(
            {
                "wake_intent": wake.as_dict(),
                "employee_wake_route": route,
            },
            self.wake_root,
            expected_node_id=NODE_ID,
        )
        self.assertTrue(result["wake_delivery"]["accepted"])
        return wake, route

    def _record_supervisor_delivery(self, wake, route, reconcile_id: str, *, status: str) -> Path:
        _write_json(
            self.runtime_root / "supervisor" / "intents" / f"{reconcile_id}.json",
            {
                "schema": INTENT_RECORD_SCHEMA,
                "reconcile_id": reconcile_id,
                "state": "planned",
                "planned_at": T0.isoformat(),
                "planned_by_cycle": int(wake.expected_lease_generation),
                "intent": {
                    "schema": RECONCILE_INTENT_SCHEMA,
                    "reconcile_id": reconcile_id,
                    "kind": "employee_wake",
                    "employee_id": EMPLOYEE_ID,
                    "assignment_id": ASSIGNMENT_ID,
                    "reason": "assignment_pending" if wake.mode == "fresh" else "assignment_resume_required",
                    "wake_intent": wake.as_dict(),
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
        path = self.runtime_root / "supervisor" / "deliveries" / f"{reconcile_id}.json"
        _write_json(
            path,
            {
                "schema": DELIVERY_STATE_SCHEMA,
                "reconcile_id": reconcile_id,
                "employee_id": EMPLOYEE_ID,
                "assignment_id": ASSIGNMENT_ID,
                "wake_id": wake.wake_id,
                "status": status,
                "created_at": T0.isoformat(),
                "updated_at": T0.isoformat(),
                "authority_policy_id": EXPECTED_AUTHORITY_POLICY,
                "transport_policy_id": "transport-routing-v1",
                "transport": "one_direct",
                "transport_authority": "core_policy",
                "capability": WAKE_CAPABILITY,
                "supervisor_leader_generation": 1,
                "dispatch_performed": True,
                "presence_id": route["presence_id"],
                "presence_generation": route["presence_generation"],
                "node_id": NODE_ID,
                "wake_attempt_id": f"attempt-{reconcile_id}",
                "task_id": f"task-{reconcile_id}",
                "error_code": None,
            },
        )
        return path

    def test_fresh_process_checkpoints_without_terminal_receipt(self):
        wake, _ = self._deliver_current_wake(now=T0, presence_generation=1)
        worker = SpecStewardWakeWorker(
            runtime_root=self.runtime_root,
            wake_root=self.wake_root,
            worker_state_root=self.state_root,
            node_id=NODE_ID,
            process_instance_id="process-a",
            lease_seconds=60,
        )
        state = worker.process_one(now=T0)
        self.assertIsNotNone(state)
        self.assertEqual(state.schema, WORKER_STATE_SCHEMA)
        self.assertEqual(state.status, "checkpointed")
        self.assertEqual(state.lease_generation, 1)
        self.assertNotEqual(state.thread_head, wake.thread_head)
        assignment = self.runtime.get_assignment(ASSIGNMENT_ID)
        self.assertEqual(assignment.state, "active")
        self.assertEqual(assignment.thread_head, state.thread_head)
        self.assertFalse(
            (self.runtime_root / "lifecycle" / "receipts" / ASSIGNMENT_ID / "000001.json").exists()
        )
        employee = self.runtime.get_employee(EMPLOYEE_ID)
        self.assertEqual(employee.executor.provider, "agentos-native-spec-audit")
        self.assertEqual(employee.executor.session_id, "")
        self.assertIsNone(worker.process_one(now=T0 + timedelta(seconds=1)))

    def test_new_process_resumes_generation_two_and_final_evidence_becomes_ready_after_supervisor_reconcile(self):
        wake1, route1 = self._deliver_current_wake(now=T0, presence_generation=1)
        delivery1 = self._record_supervisor_delivery(wake1, route1, "reconcile-o3-g1", status="awaiting_claim")
        first = SpecStewardWakeWorker(
            runtime_root=self.runtime_root,
            wake_root=self.wake_root,
            worker_state_root=self.state_root,
            node_id=NODE_ID,
            process_instance_id="process-a",
            lease_seconds=60,
        )
        state1 = first.process_one(now=T0)
        self.assertEqual(state1.status, "checkpointed")
        payload1 = json.loads(delivery1.read_text(encoding="utf-8"))
        payload1["status"] = "claimed"
        _write_json(delivery1, payload1)

        resume_time = T0 + timedelta(seconds=61)
        wake2, route2 = self._deliver_current_wake(now=resume_time, presence_generation=2)
        self.assertEqual(wake2.mode, "resume")
        self.assertEqual(wake2.expected_lease_generation, 2)
        delivery2 = self._record_supervisor_delivery(wake2, route2, "reconcile-o3-g2", status="awaiting_claim")

        second = SpecStewardWakeWorker(
            runtime_root=self.runtime_root,
            wake_root=self.wake_root,
            worker_state_root=self.state_root,
            node_id=NODE_ID,
            process_instance_id="process-b",
            lease_seconds=60,
        )
        state2 = second.process_one(now=resume_time)
        self.assertEqual(state2.status, "completed")
        self.assertEqual(state2.lease_generation, 2)
        lease = self.lifecycle.get_lease(ASSIGNMENT_ID)
        self.assertEqual(lease.generation, 2)
        self.assertEqual(lease.status, "completed")
        receipt_path = self.runtime_root / "lifecycle" / "receipts" / ASSIGNMENT_ID / "000002.json"
        self.assertTrue(receipt_path.is_file())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        serialized = json.dumps(receipt, ensure_ascii=False)
        self.assertNotIn("process-a", serialized)
        self.assertNotIn("process-b", serialized)
        self.assertNotIn("session_id", serialized)

        # The worker may finish before the next Supervisor cycle observes the claim.
        blocked = inspect_spec_steward_acceptance(self.runtime)
        self.assertFalse(blocked.ready_for_live_marker)
        self.assertFalse(blocked.checks["initial_and_resume_wakes_governed"])

        payload2 = json.loads(delivery2.read_text(encoding="utf-8"))
        payload2["status"] = "claimed"
        _write_json(delivery2, payload2)
        ready = inspect_spec_steward_acceptance(self.runtime)
        self.assertTrue(ready.ready_for_live_marker)
        self.assertFalse(ready.verified_marker_emitted)
        self.assertEqual(ready.qualifying_wake_generations, (1, 2))
        witness = json.loads(
            (self.runtime_root / "acceptance" / "spec-steward-o3-live-witness.json").read_text(encoding="utf-8")
        )
        self.assertTrue(witness["fresh_executor_or_session"])
        self.assertTrue(witness["process_boundary_observed"])
        self.assertFalse(witness["session_identity_exposed"])

    def test_same_process_resume_cannot_produce_fresh_executor_witness(self):
        self._deliver_current_wake(now=T0, presence_generation=1)
        worker = SpecStewardWakeWorker(
            runtime_root=self.runtime_root,
            wake_root=self.wake_root,
            worker_state_root=self.state_root,
            node_id=NODE_ID,
            process_instance_id="same-process",
            lease_seconds=60,
        )
        state1 = worker.process_one(now=T0)
        self.assertEqual(state1.status, "checkpointed")
        resume_time = T0 + timedelta(seconds=61)
        self._deliver_current_wake(now=resume_time, presence_generation=2)
        state2 = worker.process_one(now=resume_time)
        self.assertEqual(state2.status, "completed")
        self.assertFalse(
            (self.runtime_root / "acceptance" / "spec-steward-o3-live-witness.json").exists()
        )
        report = inspect_spec_steward_acceptance(self.runtime)
        self.assertFalse(report.ready_for_live_marker)
        self.assertFalse(report.checks["fresh_executor_or_session_live_witness"])

    def test_tampered_capsule_fails_before_claiming_assignment(self):
        wake, _ = self._deliver_current_wake(now=T0, presence_generation=1)
        capsule_path = next((self.wake_root / EMPLOYEE_ID).glob("*.json"))
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        capsule["wake_intent"]["goal"] = "tampered"
        _write_json(capsule_path, capsule)
        worker = SpecStewardWakeWorker(
            runtime_root=self.runtime_root,
            wake_root=self.wake_root,
            worker_state_root=self.state_root,
            node_id=NODE_ID,
            process_instance_id="process-a",
        )
        state = worker.process_one(now=T0)
        self.assertEqual(state.status, "failed")
        self.assertEqual(state.error_code, "worker_pre_execution_failed")
        assignment = self.runtime.get_assignment(ASSIGNMENT_ID)
        self.assertEqual(assignment.state, "pending")
        self.assertEqual(assignment.thread_head, wake.thread_head)
        self.assertIsNone(self.lifecycle.get_lease(ASSIGNMENT_ID))

    def test_worker_refuses_wake_root_inside_canonical_runtime(self):
        with self.assertRaisesRegex(ValueError, "wake_root_must_not_be_canonical_runtime"):
            SpecStewardWakeWorker(
                runtime_root=self.runtime_root,
                wake_root=self.runtime_root / "node-wake",
                worker_state_root=self.state_root,
                node_id=NODE_ID,
            )

    def test_worker_refuses_empty_runtime_instead_of_bootstrapping_shadow_employee(self):
        empty = Path(self.tmp.name) / "empty-runtime"
        with self.assertRaisesRegex(RuntimeError, "canonical_employee_missing"):
            SpecStewardWakeWorker(
                runtime_root=empty,
                wake_root=self.wake_root,
                worker_state_root=self.state_root,
                node_id=NODE_ID,
            )
        self.assertFalse((empty / "employees" / f"{EMPLOYEE_ID}.json").exists())


if __name__ == "__main__":
    unittest.main()
