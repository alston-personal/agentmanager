import json
import tempfile
import unittest
from pathlib import Path
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.core_work_items import WorkItemStore, WORK_ITEM_SCHEMA
from agentos_node.employee_worker_host_runtime import ProductEmployeeWorkerAdapterRegistry, ExactEmployeeWorkerHost
from agentos_node.hermes_worker import _is_hermes_assignment
from agentos_node.hermes_worker_cli import main
from io import StringIO
from contextlib import redirect_stdout

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/"governance/employee-worker-adapters-v2.json"
EMPLOYEE="hermes-technology-scout"
SKILL="github.technology.scan"
ROLE="research.hermes"
BASE="hermes-2120-discovery-v1"

def capsule(assignment):
    return {"employee_id":EMPLOYEE,"assignment_id":assignment,
        "wake_intent":{"role_ids":[ROLE],"skill_ids":[SKILL]}}

class HermesWorkerIntegrationTests(unittest.TestCase):
    def test_fixed_adapter_registered_in_v2(self):
        r=ProductEmployeeWorkerAdapterRegistry(CATALOG)
        a=r.resolve(capsule(BASE))
        self.assertIsNotNone(a)
        self.assertEqual(a.runner_kind,"hermes_github_scan")

    def test_dynamic_assignment_requires_canonical_authorized_work(self):
        with tempfile.TemporaryDirectory() as d:
            runtime=EmployeeRuntime(d)
            runtime.create_employee(EMPLOYEE,"Hermes",role_ids=[ROLE],skill_ids=[SKILL])
            r=ProductEmployeeWorkerAdapterRegistry(CATALOG,runtime_root=d)
            assignment=BASE+"-cycle-000001"
            self.assertIsNone(r.resolve(capsule(assignment)))
            store=WorkItemStore(runtime)
            store.persist({"schema":WORK_ITEM_SCHEMA,"work_item_id":assignment,
                "source_kind":"schedule","source_ref":"schedule:hermes-2120",
                "project_id":"agentos-core","employee_id":EMPLOYEE,
                "assignment_id":assignment,"goal":"bounded git scan",
                "required_capabilities":[SKILL],
                "authority_requirements":["one-governed-dispatch","hermes-scheduled-continuation-authorized"],
                "state":"open"})
            store.project_pending_assignment(assignment)
            self.assertEqual(r.resolve(capsule(assignment)).assignment_id,assignment)
            self.assertIsNone(r.resolve(capsule(BASE+"-cycle-9999999")))
            self.assertIsNone(r.resolve(capsule(BASE+"-unexpected")))

    def test_cli_fails_closed_without_real_one_delivery(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for path in ("runtime","wake","worker"):
                (p/path).mkdir()
            out=StringIO()
            with redirect_stdout(out):
                status=main(["--runtime-root",str(p/"runtime"),
                    "--wake-root",str(p/"wake"),
                    "--worker-state-root",str(p/"worker"),
                    "--node-id","oracle","--assignment-id",BASE,"--wake-id","wake-1",
                    "--presence-generation","1","--once"])
            self.assertEqual(status,2)
            result=json.loads(out.getvalue())
            self.assertEqual(result["status"],"failed")
            self.assertEqual(result["employee_id"],EMPLOYEE)
            self.assertEqual(result["assignment_id"],BASE)
            self.assertEqual(result["wake_id"],"wake-1")
            self.assertEqual(result["presence_generation"],1)
            self.assertEqual(result["error_code"],"hermes_wake_missing_or_ambiguous")
            self.assertFalse(result["verified_marker_emitted"])

    def test_recurring_scope_requires_six_digit_index(self):
        self.assertTrue(_is_hermes_assignment(BASE))
        self.assertTrue(_is_hermes_assignment(BASE+"-cycle-000012"))
        self.assertFalse(_is_hermes_assignment(BASE+"-cycle-12"))
        self.assertFalse(_is_hermes_assignment(BASE+"-cycle-000001/evil"))

    def test_exact_host_builds_only_allowlisted_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            host=ExactEmployeeWorkerHost(runtime_root=p/"runtime",wake_root=p/"wake",
                host_state_root=p/"host",worker_state_root=p/"worker",node_id="oracle")
            adapter=host.registry.resolve(capsule(BASE))
            host._pinned_candidate=type("Pinned",(),{"capsule":{
                "wake_id":"wake-one","presence_generation":1}})()
            cmd=host._child_command(adapter)
            self.assertIn("agentos_node.hermes_worker_cli",cmd)
            self.assertEqual(cmd[cmd.index("--assignment-id")+1],BASE)
            self.assertEqual(cmd[-4:],["--wake-id","wake-one","--presence-generation","1"])
            self.assertNotIn("--token",cmd)
            self.assertNotIn("--shell",cmd)

if __name__=="__main__":
    unittest.main()
