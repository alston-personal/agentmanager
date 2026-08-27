import tempfile
import unittest
from pathlib import Path

from agent_core.employee_runtime import EmployeeRuntime


class EmployeeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = EmployeeRuntime(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_employee_identity_survives_executor_rebind(self):
        employee = self.runtime.register_employee(
            "spec-steward-1",
            display_name="Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["task_architect"],
        )
        self.assertEqual(employee.memory_namespace, "employees/spec-steward-1/memory")

        first = self.runtime.bind_executor(
            "spec-steward-1",
            provider="openai",
            model="gpt-a",
            session_id="session-a",
        )
        second = self.runtime.bind_executor(
            "spec-steward-1",
            provider="google",
            model="gemini-b",
            session_id="session-b",
        )

        self.assertEqual(first.agent_id, second.agent_id)
        self.assertEqual(second.role_ids, ["governance.spec_steward"])
        self.assertEqual(second.memory_namespace, "employees/spec-steward-1/memory")
        self.assertEqual(second.executor.provider, "google")

    def test_assignment_head_and_state_are_durable(self):
        self.runtime.register_employee("spec-steward-1", display_name="Spec Steward")
        self.runtime.create_assignment(
            "closure-review",
            employee_id="spec-steward-1",
            goal="Review closure gaps",
            thread_head="ledger loaded",
        )
        updated = self.runtime.set_assignment_state(
            "spec-steward-1",
            "closure-review",
            "active",
            thread_head="agent employee runtime selected as P0",
        )

        reloaded = EmployeeRuntime(Path(self.temp.name)).get_assignment("spec-steward-1", "closure-review")
        self.assertEqual(updated.state, "active")
        self.assertEqual(reloaded.thread_head, "agent employee runtime selected as P0")

    def test_agent_to_agent_message_is_written_to_both_mailboxes(self):
        self.runtime.register_employee("steward", display_name="Steward")
        self.runtime.register_employee("paw", display_name="Paw")

        self.runtime.send_message(
            "msg-1",
            sender_id="steward",
            recipient_id="paw",
            subject="Implement assignment",
            payload={"goal": "Build employee runtime"},
            assignment_id="employee-runtime",
        )

        inbox = self.runtime.list_inbox("paw")
        self.assertEqual(len(inbox), 1)
        self.assertEqual(inbox[0].sender_id, "steward")
        self.assertEqual(inbox[0].assignment_id, "employee-runtime")

    def test_assignment_can_close_with_receipt_like_result(self):
        self.runtime.register_employee("paw", display_name="Paw")
        self.runtime.create_assignment(
            "impl-1",
            employee_id="paw",
            goal="Implement minimal runtime",
        )
        completed = self.runtime.set_assignment_state(
            "paw",
            "impl-1",
            "completed",
            result={"receipt": "tests-passed", "artifacts": ["agent_core/employee_runtime.py"]},
        )
        self.assertEqual(completed.state, "completed")
        self.assertEqual(completed.result["receipt"], "tests-passed")

    def test_unsafe_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.runtime.register_employee("../escape", display_name="bad")


if __name__ == "__main__":
    unittest.main()
