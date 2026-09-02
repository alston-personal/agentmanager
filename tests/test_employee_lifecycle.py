from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.employee_lifecycle import (
    LEASE_SCHEMA,
    RECEIPT_SCHEMA,
    WORK_PACKET_SCHEMA,
    EmployeeLifecycle,
)
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry


T0 = datetime(2026, 9, 2, 4, 0, 0, tzinfo=timezone.utc)


class EmployeeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
        )
        self.runtime.create_assignment(
            "audit-001",
            "spec-steward",
            "Audit open specification closure gaps",
            thread_head="ir-before-claim",
            constraints=["read-only", "receipts-over-claims"],
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def test_claim_activates_pending_assignment_and_is_idempotent_for_same_lease(self):
        lease = self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            now=T0,
        )
        self.assertEqual(lease.schema, LEASE_SCHEMA)
        self.assertEqual(lease.generation, 1)
        self.assertFalse(lease.resume_required)
        self.assertEqual(lease.prior_execution_state, "known")
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "active")
        same = self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            now=T0 + timedelta(seconds=10),
        )
        self.assertEqual(same.generation, 1)
        self.assertEqual(same.lease_id, "lease-a")

    def test_competing_claim_is_rejected_while_lease_is_live(self):
        self.lifecycle.claim("audit-001", "spec-steward", "lease-a", now=T0)
        with self.assertRaisesRegex(RuntimeError, "assignment_already_leased"):
            self.lifecycle.claim(
                "audit-001",
                "spec-steward",
                "lease-b",
                now=T0 + timedelta(seconds=30),
            )

    def test_expired_lease_reclaim_marks_prior_execution_unknown_and_preserves_thread_head(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            lease_seconds=60,
            now=T0,
        )
        self.lifecycle.checkpoint(
            "audit-001",
            "lease-a",
            "ir-checkpoint-1",
            now=T0 + timedelta(seconds=20),
        )
        resumed = self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-b",
            lease_seconds=60,
            now=T0 + timedelta(seconds=61),
        )
        self.assertEqual(resumed.generation, 2)
        self.assertTrue(resumed.resume_required)
        self.assertEqual(resumed.prior_execution_state, "unknown")
        self.assertEqual(resumed.resumed_from_lease_id, "lease-a")
        self.assertEqual(resumed.thread_head, "ir-checkpoint-1")
        self.assertEqual(
            self.runtime.get_assignment("audit-001").thread_head,
            "ir-checkpoint-1",
        )

    def test_heartbeat_extends_current_lease(self):
        lease = self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            lease_seconds=60,
            now=T0,
        )
        renewed = self.lifecycle.heartbeat(
            "audit-001",
            "lease-a",
            lease_seconds=120,
            now=T0 + timedelta(seconds=30),
        )
        self.assertNotEqual(lease.expires_at, renewed.expires_at)
        self.assertFalse(
            self.lifecycle.lease_expired(
                renewed,
                now=T0 + timedelta(seconds=100),
            )
        )

    def test_expired_owner_cannot_checkpoint(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            lease_seconds=60,
            now=T0,
        )
        with self.assertRaisesRegex(RuntimeError, "lease_expired"):
            self.lifecycle.checkpoint(
                "audit-001",
                "lease-a",
                "late-head",
                now=T0 + timedelta(seconds=61),
            )
        self.assertEqual(
            self.runtime.get_assignment("audit-001").thread_head,
            "ir-before-claim",
        )

    def test_finish_persists_receipt_before_releasing_lease(self):
        self.runtime.bind_executor(
            "spec-steward",
            provider="openai-codex-local",
            model="codex",
            session_id="private-session-id",
        )
        self.lifecycle.claim("audit-001", "spec-steward", "lease-a", now=T0)
        self.lifecycle.checkpoint(
            "audit-001",
            "lease-a",
            "ir-complete",
            now=T0 + timedelta(seconds=10),
        )
        receipt = self.lifecycle.finish(
            "audit-001",
            "lease-a",
            result_summary={"closure_gaps": 3},
            now=T0 + timedelta(seconds=20),
        )
        self.assertEqual(receipt.schema, RECEIPT_SCHEMA)
        self.assertEqual(receipt.outcome, "completed")
        self.assertEqual(receipt.thread_head, "ir-complete")
        self.assertEqual(receipt.result_summary, {"closure_gaps": 3})
        self.assertFalse(receipt.credential_exposed)
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "completed")
        self.assertEqual(self.lifecycle.get_lease("audit-001").status, "completed")
        serialized = json.dumps(receipt.__dict__ if hasattr(receipt, "__dict__") else {
            "executor_provider": receipt.executor_provider,
            "executor_model": receipt.executor_model,
            "result_summary": receipt.result_summary,
        })
        self.assertNotIn("private-session-id", serialized)

    def test_next_assignment_prefers_expired_active_work_over_new_pending(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            lease_seconds=60,
            now=T0,
        )
        self.runtime.create_assignment(
            "audit-002",
            "spec-steward",
            "Newer audit",
        )
        selected = self.lifecycle.next_assignment(
            "spec-steward",
            now=T0 + timedelta(seconds=61),
        )
        self.assertIsNotNone(selected)
        assignment, resume_required = selected
        self.assertEqual(assignment.assignment_id, "audit-001")
        self.assertTrue(resume_required)

    def test_work_packet_hydrates_roles_without_executor_session_identity(self):
        self.runtime.bind_executor(
            "spec-steward",
            provider="openai-codex-local",
            model="codex",
            session_id="must-not-leak",
        )
        self.lifecycle.claim("audit-001", "spec-steward", "lease-a", now=T0)
        registry = RoleRegistry(
            Path(__file__).resolve().parents[1] / ".agent" / "roles" / "registry.yaml"
        )
        packet = self.lifecycle.build_work_packet(
            "audit-001",
            "lease-a",
            registry,
            now=T0 + timedelta(seconds=5),
        )
        self.assertEqual(packet["schema"], WORK_PACKET_SCHEMA)
        self.assertEqual(packet["employee"]["agent_id"], "spec-steward")
        self.assertEqual(packet["roles"][0]["role_id"], "governance.spec_steward")
        self.assertIn("governance.spec.audit", packet["roles"][0]["capabilities"])
        self.assertFalse(packet["credential_exposed"])
        serialized = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("must-not-leak", serialized)


if __name__ == "__main__":
    unittest.main()
