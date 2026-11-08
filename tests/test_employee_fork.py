from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.employee_fork import EmployeeForkService
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.role_runtime import RoleRegistry

T0=datetime(2026,9,2,6,tzinfo=timezone.utc)
REGISTRY=Path(__file__).resolve().parents[1]/".agent"/"roles"/"registry.yaml"

class EmployeeForkTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.runtime=EmployeeRuntime(self.dir.name)
        self.runtime.create_employee("paw","Paw",role_ids=["sector.paw"])
        self.runtime.create_assignment("parent","paw","Bounded task",thread_head="parent-h0")
        self.lifecycle=EmployeeLifecycle(self.runtime)
        self.lifecycle.claim("parent","paw","lease-parent",now=T0)
        self.fork=EmployeeForkService(self.lifecycle,RoleRegistry(REGISTRY))

    def tearDown(self):
        self.dir.cleanup()

    def test_fork_child_has_isolated_identity_and_no_executor_or_skills(self):
        link=self.fork.fork(parent_assignment_id="parent",parent_lease_id="lease-parent",
            child_employee_id="paw-fork-1",child_assignment_id="child-1",
            goal="Inspect status",role_ids=["sector.paw"],now=T0+timedelta(seconds=5))
        child=self.runtime.get_employee("paw-fork-1")
        self.assertEqual(child.role_ids,["sector.paw"])
        self.assertEqual(child.memory_namespace,"employee:paw-fork-1")
        self.assertEqual(child.executor.provider,"unbound")
        self.assertEqual(child.skill_ids,[])
        self.assertEqual(link.parent_employee_id,"paw")
        self.assertEqual(self.runtime.get_assignment("child-1").employee_id,"paw-fork-1")
        self.assertEqual(self.runtime.get_assignment("parent").thread_head,"parent-h0")

    def test_child_cannot_inherit_extra_role(self):
        with self.assertRaisesRegex(PermissionError,"fork_role_must_be_parent_subset"):
            self.fork.fork(parent_assignment_id="parent",parent_lease_id="lease-parent",
                child_employee_id="bad-child",child_assignment_id="bad-assignment",
                goal="Escalate",role_ids=["governance.keeper"],now=T0+timedelta(seconds=5))
        with self.assertRaises(FileNotFoundError):
            self.runtime.get_employee("bad-child")

    def test_expired_parent_lease_rejects_child_identity_creation(self):
        with self.assertRaisesRegex(RuntimeError,"lease_expired"):
            self.fork.fork(parent_assignment_id="parent",parent_lease_id="lease-parent",
                child_employee_id="late-child",child_assignment_id="late-assignment",
                goal="Late",role_ids=["sector.paw"],now=T0+timedelta(seconds=301))
        with self.assertRaises(FileNotFoundError):
            self.runtime.get_employee("late-child")

    def test_complete_child_returns_only_candidate_not_promoted_experience(self):
        self.fork.fork(parent_assignment_id="parent",parent_lease_id="lease-parent",
            child_employee_id="paw-fork-1",child_assignment_id="child-1",
            goal="Inspect status",role_ids=["sector.paw"],now=T0+timedelta(seconds=5))
        self.lifecycle.claim("child-1","paw-fork-1","lease-child",now=T0+timedelta(seconds=10))
        self.lifecycle.checkpoint("child-1","lease-child","child-evidence",now=T0+timedelta(seconds=20))
        self.lifecycle.finish("child-1","lease-child",
            result_summary={"secret":"do-not-copy","status":"done"},
            now=T0+timedelta(seconds=30))
        candidate=self.fork.prepare_experience_return("child-1",now=T0+timedelta(seconds=35))
        body=str(asdict(candidate))
        self.assertIn("PENDING_ONE_REVIEW",body)
        self.assertEqual(candidate.child_receipt_generation,1)
        self.assertNotIn("do-not-copy",body)
        self.assertEqual(self.runtime.get_assignment("parent").thread_head,"parent-h0")
        second=self.fork.prepare_experience_return("child-1",now=T0+timedelta(seconds=40))
        self.assertEqual(candidate.return_id,second.return_id)

if __name__=="__main__":
    unittest.main()
