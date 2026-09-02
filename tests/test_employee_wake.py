from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import WAKE_INTENT_SCHEMA, EmployeeWakePlanner


T0 = datetime(2026, 9, 2, 5, 0, 0, tzinfo=timezone.utc)


class EmployeeWakePlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        self.runtime.bind_executor(
            "spec-steward",
            provider="openai-codex-local",
            model="codex",
            session_id="private-session-must-not-leak",
        )
        self.runtime.create_assignment(
            "audit-001",
            "spec-steward",
            "Audit open specification closure gaps",
            thread_head="ir-audit-start",
            constraints=["read-only", "receipts-over-claims"],
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.planner = EmployeeWakePlanner(self.lifecycle)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_assignment_produces_fresh_bounded_wake_intent(self):
        intent = self.planner.plan_next("spec-steward", now=T0)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.schema, WAKE_INTENT_SCHEMA)
        self.assertEqual(intent.employee_id, "spec-steward")
        self.assertEqual(intent.assignment_id, "audit-001")
        self.assertEqual(intent.mode, "fresh")
        self.assertEqual(intent.expected_lease_generation, 1)
        self.assertFalse(intent.resume_required)
        self.assertEqual(intent.prior_execution_state, "known")
        self.assertEqual(intent.thread_head, "ir-audit-start")
        self.assertEqual(intent.role_ids, ("governance.spec_steward",))
        self.assertEqual(intent.skill_ids, ("spec.audit",))
        self.assertEqual(intent.authority_boundary, "selection_only_no_execution")
        self.assertEqual(intent.executor_selection, "unbound")
        self.assertEqual(intent.transport_selection, "unbound")
        self.assertFalse(intent.credential_exposed)

        serialized = json.dumps(intent.as_dict(), ensure_ascii=False).casefold()
        self.assertNotIn("private-session-must-not-leak", serialized)
        for forbidden in (
            "node_id",
            "one_url",
            "github_actions",
            "workflow_dispatch",
            "argv",
            "executable",
            "authorization",
            "bearer ",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_repeated_planning_before_claim_is_idempotent(self):
        first = self.planner.plan_next("spec-steward", now=T0)
        second = self.planner.plan_next(
            "spec-steward", now=T0 + timedelta(seconds=20)
        )
        self.assertEqual(first.wake_id, second.wake_id)
        self.assertEqual(first.expected_lease_generation, 1)
        self.assertEqual(second.expected_lease_generation, 1)
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "pending")
        self.assertIsNone(self.lifecycle.get_lease("audit-001"))

    def test_live_lease_suppresses_duplicate_wake(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-live",
            lease_seconds=120,
            now=T0,
        )
        self.assertIsNone(
            self.planner.plan_next(
                "spec-steward", now=T0 + timedelta(seconds=30)
            )
        )

    def test_expired_assignment_produces_resume_with_unknown_prior_execution(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-old",
            lease_seconds=60,
            now=T0,
        )
        self.lifecycle.checkpoint(
            "audit-001",
            "lease-old",
            "ir-audit-checkpoint",
            now=T0 + timedelta(seconds=20),
        )
        intent = self.planner.plan_next(
            "spec-steward", now=T0 + timedelta(seconds=61)
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.mode, "resume")
        self.assertTrue(intent.resume_required)
        self.assertEqual(intent.prior_execution_state, "unknown")
        self.assertEqual(intent.expected_lease_generation, 2)
        self.assertEqual(intent.thread_head, "ir-audit-checkpoint")

        # Planning is still read-only: the old lease remains until a separately
        # authorized claimant actually takes generation 2.
        old = self.lifecycle.get_lease("audit-001")
        self.assertEqual(old.lease_id, "lease-old")
        self.assertEqual(old.generation, 1)
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "active")

    def test_resume_wake_id_is_stable_until_reclaim(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-old",
            lease_seconds=60,
            now=T0,
        )
        first = self.planner.plan_next(
            "spec-steward", now=T0 + timedelta(seconds=61)
        )
        second = self.planner.plan_next(
            "spec-steward", now=T0 + timedelta(seconds=90)
        )
        self.assertEqual(first.wake_id, second.wake_id)
        self.assertEqual(first.expected_lease_generation, 2)

    def test_completed_work_is_not_woken(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-a",
            now=T0,
        )
        self.lifecycle.finish(
            "audit-001",
            "lease-a",
            now=T0 + timedelta(seconds=10),
        )
        self.assertIsNone(
            self.planner.plan_next(
                "spec-steward", now=T0 + timedelta(seconds=20)
            )
        )

    def test_interrupted_active_work_is_selected_before_new_pending_work(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-old",
            lease_seconds=60,
            now=T0,
        )
        self.runtime.create_assignment(
            "audit-002",
            "spec-steward",
            "New audit",
            thread_head="ir-new",
        )
        intent = self.planner.plan_next(
            "spec-steward", now=T0 + timedelta(seconds=61)
        )
        self.assertEqual(intent.assignment_id, "audit-001")
        self.assertEqual(intent.mode, "resume")


if __name__ == "__main__":
    unittest.main()
