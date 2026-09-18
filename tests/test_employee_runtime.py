import tempfile
import unittest

from agent_core.employee_runtime import EmployeeRuntime
from agent_core.work_intent import WORK_INTENT_REF_SCHEMA


class EmployeeRuntimeTest(unittest.TestCase):
    def test_identity_survives_executor_rebinding(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            employee = runtime.create_employee(
                "spec-steward",
                "Spec Steward",
                role_ids=["governance.spec_steward"],
            )
            self.assertEqual(employee.memory_namespace, "employee:spec-steward")

            first = runtime.bind_executor(
                "spec-steward", provider="claude", model="claude", session_id="s1"
            )
            second = runtime.bind_executor(
                "spec-steward", provider="codex", model="gpt", session_id="s2"
            )

            self.assertEqual(first.agent_id, second.agent_id)
            self.assertEqual(second.role_ids, ["governance.spec_steward"])
            self.assertEqual(second.memory_namespace, "employee:spec-steward")
            self.assertEqual(second.executor.provider, "codex")

    def test_assignment_and_thread_head_are_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            runtime.create_employee("spec-steward", "Spec Steward")
            runtime.create_assignment(
                "spec-audit-1",
                "spec-steward",
                "audit unresolved AgentOS specs",
                thread_head="thread:root",
            )
            runtime.update_assignment(
                "spec-audit-1", state="active", thread_head="thread:spec-audit"
            )

            restarted = EmployeeRuntime(tmp)
            assignment = restarted.get_assignment("spec-audit-1")
            self.assertEqual(assignment.state, "active")
            self.assertEqual(assignment.thread_head, "thread:spec-audit")

    def test_unscoped_memory_access_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            runtime.create_employee(
                "weaver",
                "Weaver",
                role_ids=["sector.weaver"],
            )
            with self.assertRaisesRegex(
                PermissionError, "employee_memory_policy_required"
            ):
                runtime.write_memory("weaver", "current", {"spec": "A"})
            with self.assertRaisesRegex(
                PermissionError, "employee_memory_policy_required"
            ):
                runtime.read_memory("weaver", "current")

    def test_local_inbox_is_durable_but_not_cross_node_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            runtime.create_employee("weaver", "Weaver")
            runtime.create_employee("paw", "Paw")
            runtime.send_message(
                "handoff-1",
                "weaver",
                "paw",
                "implementation handoff",
                {"spec": "bounded"},
                assignment_id="a1",
            )
            restarted = EmployeeRuntime(tmp)
            inbox = restarted.list_inbox("paw")
            self.assertEqual(len(inbox), 1)
            self.assertEqual(inbox[0].sender_id, "weaver")
            self.assertEqual(inbox[0].assignment_id, "a1")

    def test_rejects_invalid_assignment_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            runtime.create_employee("keeper", "Keeper")
            runtime.create_assignment("a1", "keeper", "guard")
            with self.assertRaises(ValueError):
                runtime.update_assignment("a1", state="magically_done")


    def test_work_intent_ref_is_content_addressed_and_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            runtime.create_employee("writer", "Writer")
            runtime.create_assignment("draft-1", "writer", "review draft")
            runtime.set_work_intent_ref(
                "draft-1",
                {
                    "schema": WORK_INTENT_REF_SCHEMA,
                    "product_id": "zeus-writer",
                    "state_key": "review-existing-draft",
                    "revision": 3,
                    "digest": "sha256:" + "a" * 64,
                },
            )
            restarted = EmployeeRuntime(tmp)
            assignment = restarted.get_assignment("draft-1")
            self.assertEqual(assignment.work_intent_ref["product_id"], "zeus-writer")
            self.assertEqual(assignment.work_intent_ref["revision"], 3)

    def test_work_intent_ref_rejects_execution_authority_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EmployeeRuntime(tmp)
            runtime.create_employee("writer", "Writer")
            runtime.create_assignment("draft-1", "writer", "review draft")
            with self.assertRaisesRegex(ValueError, "invalid_work_intent_ref_fields"):
                runtime.set_work_intent_ref(
                    "draft-1",
                    {
                        "schema": WORK_INTENT_REF_SCHEMA,
                        "product_id": "zeus-writer",
                        "state_key": "review-existing-draft",
                        "revision": 1,
                        "digest": "sha256:" + "b" * 64,
                        "argv": ["python", "publish.py"],
                    },
                )


if __name__ == "__main__":
    unittest.main()
