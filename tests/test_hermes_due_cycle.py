import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from agent_core.core_work_items import WorkItemStore
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.hermes_due_cycle import project_due_hermes_cycle,EMPLOYEE,SKILL,ROOT_ITEM,REQUIRED_AUTHORITY

NOW=datetime(2026,11,9,10,tzinfo=timezone.utc)

class HermesDueCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime=EmployeeRuntime(self.temp.name)
        self.runtime.create_employee(EMPLOYEE,"Hermes",role_ids=["research.hermes"],skill_ids=[SKILL])
        self.store=WorkItemStore(self.runtime)
        self.lifecycle=EmployeeLifecycle(self.runtime)
    def prepare(self, authorized=True):
        self.store.persist({"schema":"agentos.core-work-item/v1","work_item_id":ROOT_ITEM,
            "source_kind":"schedule","source_ref":"schedule:hermes-2120","project_id":"agentos-core",
            "employee_id":EMPLOYEE,"assignment_id":ROOT_ITEM,"goal":"bounded github scan",
            "required_capabilities":[SKILL],"authority_requirements":[REQUIRED_AUTHORITY] if authorized else [],
            "source_revision":"v1","state":"open"})
        self.store.project_pending_assignment(ROOT_ITEM)
    def complete(self,hours=3):
        lease=self.lifecycle.claim(ROOT_ITEM,EMPLOYEE,"lease-1",now=NOW)
        self.lifecycle.checkpoint(ROOT_ITEM,"lease-1","scan:checkpoint",now=NOW)
        self.lifecycle.finish(ROOT_ITEM,"lease-1",now=NOW,result_summary={
           "scan_schema":"agentos.hermes-technology-scan/v1","scan_outcome":"completed","next_interval_hours":hours})
    def test_unconfigured_no_work(self):
        self.assertEqual(project_due_hermes_cycle(self.store,self.lifecycle,now=NOW)["status"],"not_configured")
    def test_explicit_authority_required(self):
        self.prepare(authorized=False)
        self.assertEqual(project_due_hermes_cycle(self.store,self.lifecycle,now=NOW)["status"],"not_authorized")
    def test_completed_but_not_due(self):
        self.prepare()
        self.complete()
        p=project_due_hermes_cycle(self.store,self.lifecycle,now=NOW+timedelta(hours=2))
        self.assertEqual(p["status"],"not_due")
    def test_create_once_and_never_duplicate(self):
        self.prepare()
        self.complete()
        p=project_due_hermes_cycle(self.store,self.lifecycle,now=NOW+timedelta(hours=3))
        self.assertEqual(p["status"],"projected")
        self.assertEqual(self.runtime.get_assignment(p["work_item_id"]).state,"pending")
        second=project_due_hermes_cycle(self.store,self.lifecycle,now=NOW+timedelta(hours=4))
        self.assertEqual(second["status"],"awaiting_terminal_receipt")
    def test_not_after_missing_scan_evidence(self):
        self.prepare()
        lease=self.lifecycle.claim(ROOT_ITEM,EMPLOYEE,"lease-1",now=NOW)
        self.lifecycle.finish(ROOT_ITEM,"lease-1",now=NOW)
        self.assertEqual(project_due_hermes_cycle(self.store,self.lifecycle,now=NOW+timedelta(days=2))["status"],"missing_scan_evidence")
    def test_not_from_unfinished_assignment(self):
        self.prepare()
        self.assertEqual(project_due_hermes_cycle(self.store,self.lifecycle,now=NOW+timedelta(days=1))["status"],"awaiting_terminal_receipt")
    def test_invalid_cadence_rejected(self):
        self.prepare()
        self.complete(hours=0)
        self.assertEqual(project_due_hermes_cycle(self.store,self.lifecycle,now=NOW+timedelta(days=2))["status"],"invalid_cadence")

if __name__=="__main__":
    unittest.main()
