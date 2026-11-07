import json
import tempfile
import unittest
from pathlib import Path
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_skills import EmployeeSkillRegistry, EmployeeSkillService
from agent_core.hermes_employee_bootstrap import ensure_hermes_employee
from agent_core.role_runtime import RoleRegistry

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = json.loads((ROOT/"governance/hermes-technology-scout-employee.json").read_text(encoding="utf-8"))

class HermesBootstrapTests(unittest.TestCase):
    def test_idempotent_and_does_not_overwrite_assignment_progress(self):
        with tempfile.TemporaryDirectory() as d:
            runtime = EmployeeRuntime(d)
            registry = RoleRegistry(ROOT/".agent/roles/registry.yaml")
            first = ensure_hermes_employee(runtime, registry, BOOTSTRAP)
            self.assertEqual(first["employee_state"],"created")
            self.assertFalse(first["continuous_operation_verified"])
            skills = EmployeeSkillService(runtime, registry, EmployeeSkillRegistry(ROOT/"governance/employee-skills.json")).hydrate_employee_skills("hermes-technology-scout")
            self.assertEqual([s.skill_id for s in skills], ["github.technology.scan"])
            self.assertFalse(skills[0].mutation_authority)
            a_id = first["assignment_id"]
            runtime.update_assignment(a_id, state="active",thread_head="checkpoint:one")
            second = ensure_hermes_employee(runtime, registry, BOOTSTRAP)
            self.assertEqual(second["assignment_state"],"preserved")
            self.assertEqual(runtime.get_assignment(a_id).thread_head, "checkpoint:one")

    def test_mismatched_identity_denied(self):
        with tempfile.TemporaryDirectory() as d:
            bad = {**BOOTSTRAP,"employee":{**BOOTSTRAP["employee"],"role_ids":["sector.paw"]}}
            with self.assertRaises(ValueError):
                ensure_hermes_employee(EmployeeRuntime(d),
                    RoleRegistry(ROOT/".agent/roles/registry.yaml"), bad)

if __name__=="__main__":
    unittest.main()
