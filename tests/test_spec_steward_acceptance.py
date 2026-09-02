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
from agent_core.employee_memory import EmployeeMemoryPolicy, EmployeeMemoryService
from agent_core.employee_presence import WAKE_CAPABILITY
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry
from agent_core.spec_steward_acceptance import (
    DEFAULT_MEMORY_POLICY_PATH,
    EXPECTED_AUTHORITY_POLICY,
    LIVE_WITNESS_SCHEMA,
    MEMORY_CLASS,
    MEMORY_EVIDENCE_SCHEMA,
    MEMORY_KEY,
    inspect_spec_steward_acceptance,
)
from agent_core.spec_steward_bootstrap import (
    DEFAULT_ROLE_REGISTRY_PATH,
    ensure_spec_steward,
)


T0 = datetime(2026, 9, 2, 6, 40, 0, tzinfo=timezone.utc)
EMPLOYEE_ID = "agentos-spec-steward"
ASSIGNMENT_ID = "spec-steward-o3-acceptance-v1"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class SpecStewardAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "runtime"
        self.runtime = EmployeeRuntime(self.root)
        ensure_spec_steward(self.runtime)
        self.lifecycle = EmployeeLifecycle(self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def _record_governed_wake(self, generation: int, suffix: str) -> None:
        reconcile_id = f"reconcile_o3_{suffix}"
        wake_id = f"wake_o3_{suffix}"
        thread_head = self.runtime.get_assignment(ASSIGNMENT_ID).thread_head
        _write_json(
            self.root / "supervisor" / "intents" / f"{reconcile_id}.json",
            {
                "schema": INTENT_RECORD_SCHEMA,
                "reconcile_id": reconcile_id,
                "state": "planned",
                "planned_at": T0.isoformat(),
                "planned_by_cycle": generation,
                "intent": {
                    "schema": RECONCILE_INTENT_SCHEMA,
                    "reconcile_id": reconcile_id,
                    "kind": "employee_wake",
                    "employee_id": EMPLOYEE_ID,
                    "assignment_id": ASSIGNMENT_ID,
                    "reason": "assignment_pending" if generation == 1 else "assignment_resume_required",
                    "wake_intent": {
                        "schema": "agentos.employee-wake-intent/v1",
                        "wake_id": wake_id,
                        "employee_id": EMPLOYEE_ID,
                        "assignment_id": ASSIGNMENT_ID,
                        "mode": "start" if generation == 1 else "resume",
                        "expected_lease_generation": generation,
                        "goal": self.runtime.get_assignment(ASSIGNMENT_ID).goal,
                        "thread_head": thread_head,
                        "constraints": list(self.runtime.get_assignment(ASSIGNMENT_ID).constraints),
                        "role_ids": ["governance.spec_steward"],
                        "skill_ids": ["spec.audit"],
                        "resume_required": generation > 1,
                        "prior_execution_state": "known" if generation == 1 else "unknown",
                        "authority_boundary": "selection_only_no_execution_authority",
                        "executor_selection": "unbound",
                        "transport_selection": "unbound",
                        "credential_exposed": False,
                    },
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
        _write_json(
            self.root / "supervisor" / "deliveries" / f"{reconcile_id}.json",
            {
                "schema": DELIVERY_STATE_SCHEMA,
                "reconcile_id": reconcile_id,
                "employee_id": EMPLOYEE_ID,
                "assignment_id": ASSIGNMENT_ID,
                "wake_id": wake_id,
                "status": "claimed",
                "created_at": T0.isoformat(),
                "updated_at": T0.isoformat(),
                "authority_policy_id": EXPECTED_AUTHORITY_POLICY,
                "transport_policy_id": "transport-routing-v1",
                "transport": "one_direct",
                "transport_authority": "core_policy",
                "capability": WAKE_CAPABILITY,
                "supervisor_leader_generation": 1,
                "dispatch_performed": True,
                "presence_id": f"presence-{suffix}",
                "presence_generation": generation,
                "node_id": "node-o3",
                "wake_attempt_id": f"attempt-{suffix}",
                "task_id": f"task-{suffix}",
                "error_code": None,
            },
        )

    def _write_memory_evidence(self, thread_head: str) -> None:
        service = EmployeeMemoryService(
            self.runtime,
            RoleRegistry(DEFAULT_ROLE_REGISTRY_PATH),
            EmployeeMemoryPolicy(DEFAULT_MEMORY_POLICY_PATH),
        )
        service.write(
            EMPLOYEE_ID,
            MEMORY_CLASS,
            MEMORY_KEY,
            {
                "schema": MEMORY_EVIDENCE_SCHEMA,
                "employee_id": EMPLOYEE_ID,
                "assignment_id": ASSIGNMENT_ID,
                "thread_head": thread_head,
                "observed_after_resume": True,
                "session_identity_exposed": False,
                "credential_exposed": False,
            },
        )

    def _write_live_witness(self, *, extra: dict | None = None) -> None:
        lease = self.lifecycle.get_lease(ASSIGNMENT_ID)
        self.assertIsNotNone(lease)
        payload = {
            "schema": LIVE_WITNESS_SCHEMA,
            "employee_id": EMPLOYEE_ID,
            "assignment_id": ASSIGNMENT_ID,
            "witness_kind": "fresh_executor_or_session_transition",
            "from_lease_id": lease.resumed_from_lease_id,
            "to_lease_id": lease.lease_id,
            "from_generation": lease.generation - 1,
            "to_generation": lease.generation,
            "fresh_executor_or_session": True,
            "process_boundary_observed": True,
            "session_identity_exposed": False,
            "credential_exposed": False,
            "observed_at": (T0 + timedelta(seconds=70)).isoformat(),
        }
        payload.update(extra or {})
        _write_json(self.root / "acceptance" / "spec-steward-o3-live-witness.json", payload)

    def _build_complete_evidence(self) -> None:
        self._record_governed_wake(1, "initial")
        self.runtime.bind_executor(
            EMPLOYEE_ID,
            provider="test-executor",
            model="model-a",
            session_id="private-session-a",
        )
        self.lifecycle.claim(
            ASSIGNMENT_ID,
            EMPLOYEE_ID,
            "lease-a",
            lease_seconds=60,
            now=T0,
        )
        self.lifecycle.checkpoint(
            ASSIGNMENT_ID,
            "lease-a",
            "o3:checkpoint:first-executor",
            now=T0 + timedelta(seconds=20),
        )

        self._record_governed_wake(2, "resume")
        self.runtime.bind_executor(
            EMPLOYEE_ID,
            provider="test-executor",
            model="model-b",
            session_id="private-session-b",
        )
        resumed = self.lifecycle.claim(
            ASSIGNMENT_ID,
            EMPLOYEE_ID,
            "lease-b",
            lease_seconds=60,
            now=T0 + timedelta(seconds=61),
        )
        self.assertTrue(resumed.resume_required)
        self.lifecycle.checkpoint(
            ASSIGNMENT_ID,
            "lease-b",
            "o3:checkpoint:resumed-executor",
            now=T0 + timedelta(seconds=65),
        )
        final_head = self.runtime.get_assignment(ASSIGNMENT_ID).thread_head
        self._write_memory_evidence(final_head)
        self._write_live_witness()
        self.lifecycle.finish(
            ASSIGNMENT_ID,
            "lease-b",
            result_summary={
                "closure_gap_count": 0,
                "acceptance_scope": "core-issue-197-o3",
            },
            now=T0 + timedelta(seconds=75),
        )

    def test_bootstrap_only_is_blocked_and_inspector_is_read_only(self):
        before = {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        report = inspect_spec_steward_acceptance(self.runtime)
        after = {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertFalse(report.ready_for_live_marker)
        self.assertFalse(report.verified_marker_emitted)
        self.assertFalse(report.checks["governed_one_wake_delivery"])
        self.assertFalse(report.checks["resumed_assignment_lease"])
        self.assertFalse(report.checks["fresh_executor_or_session_live_witness"])
        self.assertIn("terminal_sanitized_employee_receipt", report.blocking_reasons)
        self.assertEqual(report.qualifying_wake_generations, ())

    def test_complete_persisted_evidence_is_ready_but_never_emits_verified_marker(self):
        self._build_complete_evidence()
        report = inspect_spec_steward_acceptance(self.runtime)
        self.assertTrue(report.ready_for_live_marker)
        self.assertFalse(report.verified_marker_emitted)
        self.assertTrue(all(report.checks.values()))
        self.assertEqual(report.qualifying_delivery_count, 2)
        self.assertEqual(report.qualifying_wake_generations, (1, 2))
        self.assertEqual(report.observed_lease_generation, 2)
        self.assertEqual(report.terminal_receipt_generation, 2)
        serialized = json.dumps(report.as_dict(), ensure_ascii=False)
        self.assertNotIn("private-session-a", serialized)
        self.assertNotIn("private-session-b", serialized)

    def test_resume_without_initial_governed_wake_is_not_ready(self):
        self._build_complete_evidence()
        (self.root / "supervisor" / "deliveries" / "reconcile_o3_initial.json").unlink()
        report = inspect_spec_steward_acceptance(self.runtime)
        self.assertFalse(report.ready_for_live_marker)
        self.assertFalse(report.checks["initial_and_resume_wakes_governed"])
        self.assertEqual(report.qualifying_wake_generations, (2,))

    def test_live_witness_rejects_raw_session_identity_field(self):
        self._build_complete_evidence()
        self._write_live_witness(extra={"session_id": "must-not-persist"})
        report = inspect_spec_steward_acceptance(self.runtime)
        self.assertFalse(report.ready_for_live_marker)
        self.assertFalse(report.checks["fresh_executor_or_session_live_witness"])
        serialized = json.dumps(report.as_dict(), ensure_ascii=False)
        self.assertNotIn("must-not-persist", serialized)

    def test_terminal_receipt_with_secret_shaped_summary_is_rejected(self):
        self._build_complete_evidence()
        receipt_path = self.root / "lifecycle" / "receipts" / ASSIGNMENT_ID / "000002.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["result_summary"]["token"] = "ghp_should-never-be-evidence"
        _write_json(receipt_path, receipt)
        report = inspect_spec_steward_acceptance(self.runtime)
        self.assertFalse(report.ready_for_live_marker)
        self.assertFalse(report.checks["terminal_sanitized_employee_receipt"])
        self.assertFalse(report.checks["credential_and_session_identity_not_exposed"])


if __name__ == "__main__":
    unittest.main()
