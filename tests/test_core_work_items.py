from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.core_work_items import (
    EVENT_SCHEMA,
    WORK_ITEM_SCHEMA,
    WorkItemStore,
    normalize_work_item,
    observe_github_issue_event,
)
from agent_core.employee_runtime import EmployeeRuntime


class CoreWorkItemTests(unittest.TestCase):
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
        self.store = WorkItemStore(self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self):
        return {
            "schema": WORK_ITEM_SCHEMA,
            "work_item_id": "work-200-1",
            "source_kind": "github_issue",
            "source_ref": "github:alston-personal/agentmanager#200",
            "project_id": "agentos-core",
            "employee_id": "spec-steward",
            "assignment_id": "supervisor-audit-001",
            "goal": "Audit Core Supervisor closure requirements",
            "constraints": ["read-only-first", "receipts-over-claims"],
            "dependency_refs": ["github:alston-personal/agentmanager#197"],
            "required_capabilities": ["governance.spec.audit"],
            "authority_requirements": ["one-governed-dispatch"],
            "source_revision": "rev-1",
            "state": "open",
        }

    def test_issue_event_requests_reconcile_but_never_authorizes_work(self):
        event = observe_github_issue_event(
            repository="alston-personal/agentmanager",
            issue_number=200,
            event_type="updated",
            source_revision="2026-09-02T05:20:00Z",
        )
        self.assertEqual(event.schema, EVENT_SCHEMA)
        self.assertTrue(event.reconcile_requested)
        self.assertFalse(event.work_item_authorized)
        self.assertEqual(event.authority_boundary, "event_reveals_work_only")
        self.assertEqual(event.source_ref, "github:alston-personal/agentmanager#200")

    def test_event_id_is_deterministic_for_same_issue_revision(self):
        args = dict(
            repository="alston-personal/agentmanager",
            issue_number=200,
            event_type="updated",
            source_revision="rev-2",
        )
        self.assertEqual(
            observe_github_issue_event(**args).event_id,
            observe_github_issue_event(**args).event_id,
        )

    def test_work_item_uses_strict_allowlist(self):
        payload = self.payload()
        payload["arbitrary_extra"] = "must fail"
        with self.assertRaisesRegex(ValueError, "unexpected_work_item_fields"):
            normalize_work_item(payload)

    def test_source_and_dependencies_must_be_logical_refs(self):
        payload = self.payload()
        payload["source_ref"] = "https://example.invalid/issue/200"
        with self.assertRaises(ValueError):
            normalize_work_item(payload)
        payload = self.payload()
        payload["dependency_refs"] = ["/tmp/local-state"]
        with self.assertRaises(ValueError):
            normalize_work_item(payload)

    def test_persist_and_project_only_creates_pending_assignment(self):
        item = self.store.persist(self.payload())
        assignment = self.store.project_pending_assignment(item.work_item_id)
        self.assertEqual(assignment.assignment_id, "supervisor-audit-001")
        self.assertEqual(assignment.employee_id, "spec-steward")
        self.assertEqual(assignment.state, "pending")
        self.assertIsNone(assignment.result)

    def test_same_work_item_and_assignment_projection_are_idempotent(self):
        first = self.store.persist(self.payload())
        second = self.store.persist(self.payload())
        self.assertEqual(first, second)
        a = self.store.project_pending_assignment(first.work_item_id)
        b = self.store.project_pending_assignment(first.work_item_id)
        self.assertEqual(a.assignment_id, b.assignment_id)

    def test_same_work_item_id_with_changed_content_conflicts(self):
        self.store.persist(self.payload())
        changed = self.payload()
        changed["goal"] = "Different goal"
        with self.assertRaisesRegex(RuntimeError, "work_item_idempotency_conflict"):
            self.store.persist(changed)

    def test_projection_conflict_does_not_overwrite_existing_assignment(self):
        self.runtime.create_assignment(
            "supervisor-audit-001",
            "spec-steward",
            "Existing different responsibility",
        )
        item = self.store.persist(self.payload())
        with self.assertRaisesRegex(RuntimeError, "work_item_assignment_conflict"):
            self.store.project_pending_assignment(item.work_item_id)
        existing = self.runtime.get_assignment("supervisor-audit-001")
        self.assertEqual(existing.goal, "Existing different responsibility")

    def test_dependencies_require_explicit_completed_state(self):
        item = self.store.persist(self.payload())
        self.assertFalse(self.store.dependencies_ready(item.work_item_id, {}))
        self.assertFalse(
            self.store.dependencies_ready(
                item.work_item_id,
                {"github:alston-personal/agentmanager#197": "open"},
            )
        )
        self.assertTrue(
            self.store.dependencies_ready(
                item.work_item_id,
                {"github:alston-personal/agentmanager#197": "completed"},
            )
        )

    def test_closed_work_item_cannot_project_new_assignment(self):
        payload = self.payload()
        payload["state"] = "completed"
        item = self.store.persist(payload)
        with self.assertRaisesRegex(RuntimeError, "work_item_not_open"):
            self.store.project_pending_assignment(item.work_item_id)


if __name__ == "__main__":
    unittest.main()
