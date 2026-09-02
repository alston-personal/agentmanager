from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.core_supervisor import (
    RECONCILE_INTENT_SCHEMA,
    CoreSupervisorReconciler,
)
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime


T0 = datetime(2026, 9, 2, 5, 20, 0, tzinfo=timezone.utc)


class CoreSupervisorReconcilerTests(unittest.TestCase):
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
            provider="executor-must-not-authorize-supervisor",
            model="private-model",
            session_id="private-session",
        )
        self.runtime.create_assignment(
            "audit-001",
            "spec-steward",
            "Audit open specification closure gaps",
            thread_head="ir:start",
            constraints=["read-only"],
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.supervisor = CoreSupervisorReconciler(self.lifecycle)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_assignment_emits_authority_neutral_intent(self):
        plan = self.supervisor.reconcile(now=T0)
        self.assertEqual(len(plan.intents), 1)
        intent = plan.intents[0]
        self.assertEqual(intent.schema, RECONCILE_INTENT_SCHEMA)
        self.assertEqual(intent.kind, "employee_wake")
        self.assertEqual(intent.reason, "assignment_pending")
        self.assertEqual(intent.employee_id, "spec-steward")
        self.assertEqual(intent.assignment_id, "audit-001")
        self.assertEqual(intent.node_selection, "unbound")
        self.assertEqual(intent.executor_selection, "unbound")
        self.assertEqual(intent.transport_selection, "unbound")
        self.assertEqual(intent.capability_authority, "unbound")
        self.assertFalse(intent.credential_exposed)

        serialized = json.dumps(plan.as_dict(), ensure_ascii=False).casefold()
        self.assertNotIn("private-session", serialized)
        self.assertNotIn("private-model", serialized)
        self.assertNotIn("executor-must-not-authorize-supervisor", serialized)
        for forbidden in (
            "github_actions",
            "workflow_dispatch",
            "one_url",
            "executable",
            "argv",
            "bearer ",
            "authorization",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_same_state_produces_same_reconcile_id(self):
        first = self.supervisor.reconcile(now=T0).intents[0]
        second = self.supervisor.reconcile(now=T0 + timedelta(seconds=10)).intents[0]
        self.assertEqual(first.reconcile_id, second.reconcile_id)
        self.assertEqual(first.wake_intent.wake_id, second.wake_intent.wake_id)
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "pending")
        self.assertIsNone(self.lifecycle.get_lease("audit-001"))

    def test_persisted_same_intent_suppresses_duplicate_dispatch_candidate(self):
        first = self.supervisor.reconcile(now=T0).intents[0]
        plan = self.supervisor.reconcile(
            now=T0 + timedelta(seconds=5),
            persisted_reconcile_ids=[first.reconcile_id],
        )
        self.assertEqual(plan.intents, [])
        self.assertEqual(len(plan.suppressed), 1)
        self.assertEqual(plan.suppressed[0].reason, "reconcile_intent_already_persisted")

    def test_live_assignment_lease_suppresses_duplicate_wake(self):
        self.lifecycle.claim(
            "audit-001",
            "spec-steward",
            "lease-live",
            lease_seconds=120,
            now=T0,
        )
        plan = self.supervisor.reconcile(now=T0 + timedelta(seconds=30))
        self.assertEqual(plan.intents, [])
        self.assertEqual(plan.suppressed[0].reason, "no_runnable_assignment")

    def test_expired_lease_emits_resume_unknown(self):
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
            "ir:checkpoint",
            now=T0 + timedelta(seconds=20),
        )
        intent = self.supervisor.reconcile(now=T0 + timedelta(seconds=61)).intents[0]
        self.assertEqual(intent.reason, "assignment_resume_required")
        self.assertTrue(intent.wake_intent.resume_required)
        self.assertEqual(intent.wake_intent.prior_execution_state, "unknown")
        self.assertEqual(intent.wake_intent.thread_head, "ir:checkpoint")
        self.assertEqual(intent.wake_intent.expected_lease_generation, 2)

    def test_blocked_dependency_suppresses_without_mutating_assignment(self):
        plan = self.supervisor.reconcile(
            now=T0,
            blocked_assignment_ids=["audit-001"],
        )
        self.assertEqual(plan.intents, [])
        self.assertEqual(plan.suppressed[0].reason, "dependencies_blocked")
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "pending")

    def test_terminal_assignment_is_not_woken(self):
        self.lifecycle.claim("audit-001", "spec-steward", "lease-a", now=T0)
        self.lifecycle.finish(
            "audit-001",
            "lease-a",
            now=T0 + timedelta(seconds=10),
        )
        plan = self.supervisor.reconcile(now=T0 + timedelta(seconds=20))
        self.assertEqual(plan.intents, [])
        self.assertEqual(plan.suppressed[0].reason, "no_runnable_assignment")

    def test_missing_or_malformed_employee_fails_closed(self):
        missing = self.supervisor.reconcile(employee_ids=["missing-employee"], now=T0)
        self.assertEqual(missing.intents, [])
        self.assertEqual(missing.errors[0]["disposition"], "fail_closed_no_intent")

        (self.runtime.employees_dir / "broken.json").parent.mkdir(parents=True, exist_ok=True)
        (self.runtime.employees_dir / "broken.json").write_text("[]", encoding="utf-8")
        malformed = self.supervisor.reconcile(employee_ids=["broken"], now=T0)
        self.assertEqual(malformed.intents, [])
        self.assertEqual(malformed.errors[0]["disposition"], "fail_closed_no_intent")

    def test_discovery_is_deterministic_and_does_not_treat_issue_text_as_work(self):
        self.runtime.create_employee("writer", "Writer", role_ids=["sector.weaver"])
        ids = self.supervisor.discover_employee_ids()
        self.assertEqual(ids, ["spec-steward", "writer"])

        # The kernel has no Issue/body/prompt input surface at all. Free-form event
        # text cannot become execution authority in S1.
        plan = self.supervisor.reconcile(employee_ids=["writer"], now=T0)
        self.assertEqual(plan.intents, [])


if __name__ == "__main__":
    unittest.main()
