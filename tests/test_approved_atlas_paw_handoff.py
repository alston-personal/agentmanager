import json
import tempfile
import unittest
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.core_work_items import WorkItemStore
from scripts.approved_atlas_paw_handoff import handoff, WORK_ID, ASSIGNMENT_ID


class AtlasApprovedHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.ledger = self.base / "work-items.json"
        self.runtime = EmployeeRuntime(self.base / "employee-runtime")
        self.runtime.create_employee(
            "the-paw", "The Paw", role_ids=["sector.paw"],
            skill_ids=["engineering.work.inspect"],
        )
        self.item = {
            "work_id": WORK_ID, "project_id": "agentos-atlas",
            "source": "https://github.com/alston-personal/agentmanager/issues/2243",
            "owner": "role://completion.controller",
            "intake_kind": "engineering", "execution_authorized": False,
            "status": "accepted", "acceptance": ["one live Atlas ingress/resume receipt"],
        }
        self.store()

    def store(self):
        self.ledger.write_text(json.dumps({
            "schema": "agentos.work-completion/v1", "items": {WORK_ID: self.item}
        }), encoding="utf-8")

    def test_approved_creates_exact_readonly_assignment_idempotently(self):
        first = handoff(completion_state=self.ledger, runtime_root=self.runtime.root)
        second = handoff(completion_state=self.ledger, runtime_root=self.runtime.root)
        self.assertEqual(first, second)
        self.assertTrue(first["assignment_registered"])
        self.assertFalse(first["execution_authorized"])
        self.assertFalse(first["execution_started"])
        self.assertIsNone(first["lease_id"])
        item = WorkItemStore(self.runtime).get(ASSIGNMENT_ID)
        self.assertEqual(item.required_capabilities, ("engineering.work.inspect",))
        self.assertIn("read-only-inspection-only", item.authority_requirements)
        self.assertEqual(self.runtime.get_assignment(ASSIGNMENT_ID).state, "pending")
        self.assertEqual(len(list(self.runtime.assignments_dir.glob("*.json"))), 1)

    def test_missing_work_item_is_non_mutating(self):
        self.ledger.write_text(json.dumps({
            "schema": "agentos.work-completion/v1", "items": {}
        }), encoding="utf-8")
        result = handoff(completion_state=self.ledger, runtime_root=self.runtime.root)
        self.assertFalse(result["assignment_registered"])
        self.assertEqual(result["status"], "source_work_item_missing")
        self.assertFalse((self.runtime.assignments_dir / (ASSIGNMENT_ID + ".json")).exists())

    def test_wrong_identity_and_authority_fail_closed(self):
        for key, bad in (
            ("execution_authorized", True),
            ("owner", "role://lobster"),
            ("project_id", "wrong-project"),
            ("source", "https://github.com/other/repo/issues/2243"),
            ("intake_kind", "readonly"),
        ):
            original = self.item[key]
            self.item[key] = bad
            self.store()
            with self.assertRaises(PermissionError):
                handoff(completion_state=self.ledger, runtime_root=self.runtime.root)
            self.item[key] = original
        self.assertFalse((self.runtime.assignments_dir / (ASSIGNMENT_ID + ".json")).exists())

    def test_waiting_and_terminal_not_reclaimed(self):
        for status in ("waiting_external", "blocked", "done"):
            self.item["status"] = status
            self.store()
            result = handoff(completion_state=self.ledger, runtime_root=self.runtime.root)
            self.assertEqual(result["status"], "waiting_for_completion_controller")
            self.assertFalse(result["assignment_registered"])
        self.assertFalse((self.runtime.assignments_dir / (ASSIGNMENT_ID + ".json")).exists())

    def test_missing_acceptance_denied(self):
        self.item["acceptance"] = []
        self.store()
        with self.assertRaises(PermissionError):
            handoff(completion_state=self.ledger, runtime_root=self.runtime.root)


if __name__ == "__main__":
    unittest.main()
