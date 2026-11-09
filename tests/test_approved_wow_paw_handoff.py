import json
from pathlib import Path
import tempfile
import unittest

from agent_core.employee_runtime import EmployeeRuntime
from scripts.approved_wow_paw_handoff import handoff, WORK_ID, ASSIGNMENT_ID

class ApprovedWoWPawHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "work-items.json"
        self.runtime = EmployeeRuntime(self.root / "employee-runtime")
        self.runtime.create_employee("the-paw", "The Paw", role_ids=["sector.paw"],skill_ids=["engineering.work.inspect"])
        self.item = {
            "work_id":WORK_ID,
            "project_id":"wow-agentos-interface",
            "source":"https://github.com/alston-personal/agentmanager/issues/2134",
            "owner":"role://completion.controller",
            "intake_kind":"engineering",
            "execution_authorized":False,
            "status":"accepted",
            "acceptance":["two real game answers"],
        }
        self.store()

    def store(self):
        self.ledger.write_text(json.dumps({"schema":"agentos.work-completion/v1","items":{WORK_ID:self.item}}))

    def test_idempotent_and_inspect_only(self):
        first=handoff(completion_state=self.ledger,runtime_root=self.runtime.root)
        second=handoff(completion_state=self.ledger,runtime_root=self.runtime.root)
        self.assertEqual(first,second)
        self.assertEqual(first["assignment_id"],ASSIGNMENT_ID)
        self.assertFalse(first["execution_started"])
        self.assertFalse(first["execution_authorized"])
        assignment=self.runtime.get_assignment(ASSIGNMENT_ID)
        self.assertEqual(assignment.employee_id,"the-paw")
        self.assertEqual(assignment.state,"pending")
        from agent_core.core_work_items import WorkItemStore
        item=WorkItemStore(self.runtime).get(ASSIGNMENT_ID)
        self.assertEqual(item.required_capabilities,("engineering.work.inspect",))
        self.assertNotIn("write",item.required_capabilities)
        self.assertIn("one-governed-dispatch",item.authority_requirements)

    def test_authority_rejections_and_no_creation(self):
        for field,value in (
            ("execution_authorized",True),
            ("owner","role://lobster"),
            ("project_id","wrong-project"),
            ("source","https://github.com/evil/repo/issues/2134"),
            ("status","done"),
        ):
            before=self.item[field]
            self.item[field]=value
            self.store()
            with self.assertRaises((ValueError,PermissionError)):
                handoff(completion_state=self.ledger,runtime_root=self.runtime.root)
            self.item[field]=before
        self.assertFalse((self.runtime.assignments_dir / (ASSIGNMENT_ID+".json")).exists())

if __name__=="__main__":
    unittest.main()
