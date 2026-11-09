"""Execute the *real* Hermes Worker twice with controlled S4 fixtures.

No external I/O, no bypass of production verifier, and no synthetic production
receipt. This is a CI integration regression only.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_wake import EmployeeWakePlanner
from agent_core.hermes_due_cycle import project_due_hermes_cycle
from agentos_node.employee_wake_inbox import WAKE_RECEIPT_SCHEMA, WAKE_ROUTE_SCHEMA
from agentos_node.hermes_metadata_feed import SCHEMA as SNAPSHOT_SCHEMA, snapshot_path, _stamp
from agentos_node.hermes_worker import EMPLOYEE, process_exact

BASE="hermes-2120-discovery-v1"
SKILL="github.technology.scan"
ROLE="research.hermes"
NODE="oracle-employee-wake-node"

def candidate(repo):
    return {
        "full_name":repo,
        "pushed_at":"2026-11-09T00:00:00Z",
        "license":{"spdx_id":"MIT"},
        "default_branch":"main",
        "stargazers_count":5,
    }

class HermesTwoCycleRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.runtime=EmployeeRuntime(self.root/"runtime")
        self.runtime.create_employee(EMPLOYEE,"Hermes",role_ids=[ROLE],skill_ids=[SKILL])
        self.work=WorkItemStore(self.runtime)
        self.lifecycle=EmployeeLifecycle(self.runtime)
        self.wake=self.root/"wake"
        self.state=self.root/"state"
        self.wake.mkdir()
        self.state.mkdir()
        self.work.persist({
            "schema":WORK_ITEM_SCHEMA,
            "work_item_id":BASE,"source_kind":"schedule",
            "source_ref":"schedule:hermes-2120",
            "project_id":"agentos-core","employee_id":EMPLOYEE,
            "assignment_id":BASE,"goal":"bounded public GitHub scan",
            "required_capabilities":[SKILL],
            "authority_requirements":["one-governed-dispatch",
                                      "hermes-scheduled-continuation-authorized"],
            "state":"open",
        })
        self.work.project_pending_assignment(BASE)

    def _prepare_authorized_wake(self, assignment):
        planned=EmployeeWakePlanner(self.lifecycle).plan_next(EMPLOYEE)
        self.assertEqual(planned.assignment_id,assignment)
        intent=planned.as_dict()
        route={
            "schema":WAKE_ROUTE_SCHEMA, "employee_id":EMPLOYEE,
            "node_id":NODE, "presence_id":"presence-hermes-1",
            "presence_generation":1,
        }
        raw=json.dumps(
            {"wake_intent":intent,"employee_wake_route":route},
            sort_keys=True,separators=(",",":"),ensure_ascii=False,
        ).encode()
        cap={
            "schema":WAKE_RECEIPT_SCHEMA,
            "employee_id":EMPLOYEE,"assignment_id":assignment,
            "node_id":NODE,"presence_id":route["presence_id"],
            "presence_generation":1,"wake_id":planned.wake_id,
            "wake_intent":intent,"employee_wake_route":route,
            "digest":hashlib.sha256(raw).hexdigest(),
        }
        location=self.wake/EMPLOYEE
        location.mkdir(parents=True,exist_ok=True)
        (location/(planned.wake_id+".json")).write_text(
            json.dumps(cap),encoding="utf-8",
        )
        names=["paperclipai/paperclip","ruvnet/RuView"]
        snapshot={
            "schema":SNAPSHOT_SCHEMA,"employee_id":EMPLOYEE,
            "assignment_id":assignment,"wake_id":planned.wake_id,
            "presence_generation":1,
            "observed_at":datetime.now(timezone.utc).isoformat(),
            "sources":{name:candidate(name) for name in names},
            "failure_count":0,
        }
        snapshot["sha256"]=_stamp(snapshot)
        dest=snapshot_path(self.state,assignment,planned.wake_id)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(snapshot),encoding="utf-8")
        return planned

    def test_two_real_worker_execution_paths_produce_distinct_receipts(self):
        initial=self._prepare_authorized_wake(BASE)
        with patch("agentos_node.hermes_worker._verify_delivery",return_value=None):
            result=process_exact(runtime_root=self.runtime.root,
                wake_root=self.wake,worker_state_root=self.state,
                node_id=NODE,wake_id=initial.wake_id,presence_generation=1,
                assigned_id=BASE)
        self.assertEqual(result["status"],"completed")
        self.assertEqual(result["lease_generation"],1)
        a=self.runtime.get_assignment(BASE)
        self.assertEqual(a.state,"completed")
        first=self.lifecycle._receipt_path(BASE,1)
        self.assertTrue(first.is_file())
        first_data=json.loads(first.read_text())
        self.assertEqual(first_data["result_summary"]["scan_outcome"],"completed")
        self.assertFalse(first_data["credential_exposed"])

        due=datetime.fromisoformat(first_data["recorded_at"].replace("Z","+00:00")) + timedelta(hours=168)
        projected=project_due_hermes_cycle(self.work,self.lifecycle,now=due)
        self.assertEqual(projected["status"],"projected")
        next_id=projected["work_item_id"]
        self.assertEqual(self.runtime.get_assignment(next_id).state,"pending")
        second=self._prepare_authorized_wake(next_id)
        with patch("agentos_node.hermes_worker._verify_delivery",return_value=None):
            later=process_exact(runtime_root=self.runtime.root,
                wake_root=self.wake,worker_state_root=self.state,
                node_id=NODE,wake_id=second.wake_id,presence_generation=1,
                assigned_id=next_id)
        self.assertEqual(later["status"],"completed")
        self.assertNotEqual(second.wake_id,initial.wake_id)
        self.assertEqual(self.runtime.get_assignment(next_id).state,"completed")
        self.assertTrue(self.lifecycle._receipt_path(next_id,1).is_file())
        self.assertEqual(len(list((self.runtime.root/"supervisor"/"receipt-events").glob("*.json"))),2)

    def test_mismatched_assignment_never_claimed(self):
        wake=self._prepare_authorized_wake(BASE)
        with patch("agentos_node.hermes_worker._verify_delivery",return_value=None):
            with self.assertRaises(PermissionError):
                process_exact(runtime_root=self.runtime.root,wake_root=self.wake,
                    worker_state_root=self.state,node_id=NODE,
                    wake_id=wake.wake_id,presence_generation=1,
                    assigned_id=BASE+"-cycle-999999")
        self.assertEqual(self.runtime.get_assignment(BASE).state,"pending")
        self.assertIsNone(self.lifecycle.get_lease(BASE))


if __name__=="__main__":
    unittest.main()
