import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from scripts.completion_watchdog_tick import tick
from scripts.work_completion import register_intake_envelope, INTAKE_SCHEMA, load, save
from agent_core.employee_runtime import EmployeeRuntime

WORK_ID="gh-issue-2134-engineering"
ASSIGNMENT_ID="paw-wow-2134-inspect-v1"

class CompletionChronosTickTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.ledger=self.root/"governance"/"work-items.json"
        runtime=EmployeeRuntime(self.root/"employee-runtime")
        runtime.create_employee("the-paw","The Paw",
                                role_ids=["sector.paw"],skill_ids=["engineering.work.inspect"])
        register_intake_envelope(self.ledger,{
            "schema":INTAKE_SCHEMA,"intake_kind":"engineering",
            "work_id":WORK_ID, "project_id":"wow-agentos-interface",
            "title":"WoW MVP", "next_action":"Inspect WoW Bridge MVP",
            "acceptance":["verified installation"],
            "source":"https://github.com/alston-personal/agentmanager/issues/2134"
        })

    def set_wait(self, due, *, retries=1):
        state=load(self.ledger)
        item=state["items"][WORK_ID]
        item["status"]="waiting_external"
        item["wake_condition"]={"kind":"time","not_before":due}
        item["last_blocker_kind"]="VERIFICATION"
        item["machine_retry_count"]=retries
        save(self.ledger,state)

    def test_due_wakes_and_registers_once(self):
        self.set_wait("2026-01-01T00:00:00+00:00")
        at=datetime(2026,11,9,tzinfo=timezone.utc)
        first=tick(self.root,at=at)
        second=tick(self.root,at=at)
        self.assertTrue(first["awakened_wow"])
        self.assertTrue(first["paw_registered"])
        self.assertFalse(second["awakened_wow"])
        self.assertTrue(second["paw_registered"])
        self.assertEqual(load(self.ledger)["items"][WORK_ID]["status"],"accepted")
        assignment=EmployeeRuntime(self.root/"employee-runtime").get_assignment(ASSIGNMENT_ID)
        self.assertEqual(assignment.state,"pending")

    def test_future_wait_never_dispatches(self):
        self.set_wait("2030-01-01T00:00:00+00:00")
        out=tick(self.root,at=datetime(2026,11,9,tzinfo=timezone.utc))
        self.assertEqual(out["paw_projection"],"waiting_for_completion_controller")
        self.assertFalse(out["paw_registered"])
        self.assertFalse((self.root/"employee-runtime"/"assignments"/(ASSIGNMENT_ID+".json")).exists())

    def test_retry_budget_exhaustion_does_not_reopen(self):
        self.set_wait("2026-01-01T00:00:00+00:00",retries=5)
        out=tick(self.root,at=datetime(2026,11,9,tzinfo=timezone.utc))
        self.assertTrue(out["paw_registered"])
        self.assertEqual(load(self.ledger)["items"][WORK_ID]["status"],"blocked")
        from agent_core.employee_runtime import EmployeeRuntime
        self.assertEqual(EmployeeRuntime(self.root/"employee-runtime").get_assignment(ASSIGNMENT_ID).state, "pending")

if __name__=="__main__":
    unittest.main()
