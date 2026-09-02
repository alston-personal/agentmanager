from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.spec_steward_bootstrap import (
    DEFAULT_CONTRACT_PATH,
    build_spec_steward_audit_request,
    ensure_spec_steward,
    load_spec_steward_contract,
)


class SpecStewardBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root / "employee-runtime")

    def tearDown(self):
        self.tmp.cleanup()

    def test_contract_is_bounded_to_issue_197_o3(self):
        contract = load_spec_steward_contract()
        self.assertEqual(contract.employee.employee_id, "agentos-spec-steward")
        self.assertEqual(contract.employee.role_ids, ("governance.spec_steward",))
        self.assertEqual(contract.employee.skill_ids, ("spec.audit",))
        self.assertEqual(contract.initial_work_item.project_id, "agentos-core")
        self.assertEqual(contract.initial_work_item.source_ref, "core:issue-197-o3")
        self.assertEqual(contract.initial_work_item.required_capabilities, ("governance.spec.audit",))
        self.assertIn("read-only-governance-audit", contract.initial_work_item.constraints)
        self.assertIn("static_ci_cannot_emit_verified_marker", contract.invariants)

    def test_first_ensure_materializes_exact_employee_work_item_assignment_and_thread(self):
        result = ensure_spec_steward(self.runtime)
        self.assertTrue(result.employee_created)
        self.assertTrue(result.work_item_created)
        self.assertTrue(result.assignment_created)
        self.assertTrue(result.initial_thread_seeded)
        self.assertFalse(result.verified_marker_emitted)
        self.assertEqual(result.execution_authority, "not_granted_by_bootstrap")
        self.assertEqual(result.transport_selection, "unbound")
        self.assertEqual(result.executor_selection, "unbound")
        self.assertFalse(result.credential_exposed)
        self.assertEqual(result.hydrated_skill_ids, ("spec.audit",))
        self.assertIn("governance.spec.audit", result.role_capabilities)

        employee = self.runtime.get_employee("agentos-spec-steward")
        self.assertEqual(employee.role_ids, ["governance.spec_steward"])
        self.assertEqual(employee.skill_ids, ["spec.audit"])
        self.assertEqual(employee.memory_namespace, "employee:agentos-spec-steward")
        self.assertEqual(employee.executor.provider, "unbound")
        self.assertEqual(employee.executor.session_id, "")

        assignment = self.runtime.get_assignment("spec-steward-o3-acceptance-v1")
        self.assertEqual(assignment.state, "pending")
        self.assertEqual(assignment.thread_head, "o3:spec-steward-acceptance:start")
        self.assertIn("scope-is-core-issue-197-o3-only", assignment.constraints)
        self.assertFalse((self.runtime.root / "realm" / "employee-presence").exists())
        self.assertFalse((self.runtime.root / "supervisor" / "deliveries").exists())

    def test_second_ensure_is_idempotent_and_does_not_reset_runtime_state(self):
        first = ensure_spec_steward(self.runtime)
        employee_before = self.runtime.get_employee(first.employee_id)
        assignment_before = self.runtime.get_assignment(first.assignment_id)

        second = ensure_spec_steward(self.runtime)
        self.assertFalse(second.employee_created)
        self.assertFalse(second.work_item_created)
        self.assertFalse(second.assignment_created)
        self.assertFalse(second.initial_thread_seeded)
        employee_after = self.runtime.get_employee(first.employee_id)
        assignment_after = self.runtime.get_assignment(first.assignment_id)
        self.assertEqual(employee_after.created_at, employee_before.created_at)
        self.assertEqual(assignment_after.created_at, assignment_before.created_at)
        self.assertEqual(assignment_after.thread_head, assignment_before.thread_head)

    def test_ensure_preserves_progressed_thread_and_terminal_assignment(self):
        result = ensure_spec_steward(self.runtime)
        self.runtime.update_assignment(
            result.assignment_id,
            state="completed",
            thread_head="o3:checkpoint:terminal",
            result={"schema": "test-terminal-evidence", "ok": True},
        )
        again = ensure_spec_steward(self.runtime)
        self.assertEqual(again.assignment_state, "completed")
        self.assertEqual(again.thread_head, "o3:checkpoint:terminal")
        self.assertFalse(again.initial_thread_seeded)
        assignment = self.runtime.get_assignment(result.assignment_id)
        self.assertEqual(assignment.state, "completed")
        self.assertEqual(assignment.thread_head, "o3:checkpoint:terminal")
        self.assertEqual(assignment.result["schema"], "test-terminal-evidence")

    def test_existing_employee_identity_contract_drift_fails_closed(self):
        self.runtime.create_employee(
            "agentos-spec-steward",
            "Wrong Name",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        with self.assertRaisesRegex(RuntimeError, "spec_steward_employee_contract_conflict"):
            ensure_spec_steward(self.runtime)
        self.assertFalse((self.runtime.root / "supervisor" / "work-items").exists())

    def test_audit_request_is_intent_only_and_requires_downstream_authority(self):
        ensure_spec_steward(self.runtime)
        request = build_spec_steward_audit_request(self.runtime)
        self.assertEqual(request["skill"]["skill_id"], "spec.audit")
        self.assertEqual(request["intent"], "audit")
        self.assertEqual(request["args"]["scope"], "core-issue-197-o3")
        self.assertEqual(request["capability_authorization"], "required_downstream")
        self.assertEqual(request["execution_authority"], "external_governed_dispatcher")
        self.assertEqual(request["executor_selection"], "unbound")
        self.assertEqual(request["transport_selection"], "unbound")
        self.assertFalse(request["credential_exposed"])
        encoded = json.dumps(request, sort_keys=True).casefold()
        for forbidden in ("shell.exec", "workflow_dispatch", "github_actions", "bearer ", "token="):
            self.assertNotIn(forbidden, encoded)

    def test_unknown_bootstrap_field_is_rejected(self):
        raw = json.loads(DEFAULT_CONTRACT_PATH.read_text(encoding="utf-8"))
        raw["executor"] = {"provider": "anything"}
        path = self.root / "bad-bootstrap.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected_spec_steward_bootstrap_fields"):
            load_spec_steward_contract(path)


if __name__ == "__main__":
    unittest.main()
