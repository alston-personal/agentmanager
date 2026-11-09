"""No generic network permissions added to the shared Employee Worker Host."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_wake import EmployeeWakePlanner
from unittest.mock import patch
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.core_work_items import WorkItemStore
from agentos_node.hermes_metadata_feed import (
    SCHEMA, EMPLOYEE, ROSTER, _stamp, snapshot_path, validate_snapshot, produce_snapshot
)

ASSIGNMENT="hermes-2120-discovery-v1"

def meta(repo):
    return {"full_name":repo,"pushed_at":"2026-11-06T00:00:00Z",
            "license":{"spdx_id":"MIT"},"default_branch":"main",
            "stargazers_count":3}

class HermesMetadataFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.runtime=EmployeeRuntime(self.root/"runtime")
        self.runtime.create_employee(EMPLOYEE,"Hermes",role_ids=["research.hermes"],
                                     skill_ids=["github.technology.scan"])
        self.store=WorkItemStore(self.runtime)
        self.wake_root=self.root/"wake"
        self.wake_root.mkdir()
        self.state_root=self.root/"state"
    def authorize(self):
        self.store.persist({
          "schema":"agentos.core-work-item/v1","work_item_id":ASSIGNMENT,
          "source_kind":"schedule","source_ref":"schedule:hermes-2120",
          "project_id":"agentos-core","employee_id":EMPLOYEE,
          "assignment_id":ASSIGNMENT,"goal":"scan GitHub metadata",
          "required_capabilities":["github.technology.scan"],
          "authority_requirements":["hermes-scheduled-continuation-authorized",
                                    "one-governed-dispatch"],"state":"open"})
        self.store.project_pending_assignment(ASSIGNMENT)
    def capsule(self):
        planned=EmployeeWakePlanner(EmployeeLifecycle(self.runtime)).plan_next(EMPLOYEE)
        if planned is None:
            raise RuntimeError("missing_governed_test_intent")
        return {"employee_id":EMPLOYEE,"assignment_id":ASSIGNMENT,
                "wake_id":planned.wake_id,"presence_generation":1,
                "wake_intent":planned.as_dict()}
    def produce(self,fetch=meta):
        return produce_snapshot(runtime_root=self.runtime.root,wake_root=self.wake_root,
            state_root=self.state_root,capsule=self.capsule(),fetch=fetch)
    def expire_lease(self):
        lifecycle=EmployeeLifecycle(self.runtime)
        lifecycle.claim(ASSIGNMENT,EMPLOYEE,"prior-lease",
            now=datetime.now(timezone.utc)-timedelta(minutes=10))
        return lifecycle
    def test_no_authority_no_network_fetch(self):
        requested=[]
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",return_value=None):
            with self.assertRaises((PermissionError,FileNotFoundError)):
                self.produce(lambda repo:requested.append(repo))
        self.assertEqual(requested,[])
    def test_snapshot_bound_to_one_canonical_wake(self):
        self.authorize()
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",return_value=None):
            first=self.produce()
            self.assertEqual(first["status"],"materialized")
            self.assertLessEqual(first["source_count"],6)
            again=self.produce(lambda _: (_ for _ in ()).throw(AssertionError("unexpected fetch")))
            self.assertEqual(again["status"],"already_present")
        p=snapshot_path(self.state_root,ASSIGNMENT,self.capsule()["wake_id"])
        snapshot=json.loads(p.read_text())
        data=validate_snapshot(snapshot,assignment_id=ASSIGNMENT,wake_id=self.capsule()["wake_id"],presence_generation=1)
        self.assertIn("ruvnet/RuView",data)
        with self.assertRaises(PermissionError):
            validate_snapshot(snapshot,assignment_id=ASSIGNMENT,
                              wake_id="unrelated",presence_generation=1)
    def test_tampering_fails(self):
        self.authorize()
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",return_value=None):
            self.produce()
        p=snapshot_path(self.state_root,ASSIGNMENT,WAKE)
        value=json.loads(p.read_text())
        value["sources"][ROSTER[0]]["full_name"]="other/identity"
        with self.assertRaises(PermissionError):
            validate_snapshot(value,assignment_id=ASSIGNMENT,
                              wake_id=WAKE,presence_generation=1)
    def test_producer_failure_does_not_create_fake_snapshot(self):
        self.authorize()
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",return_value=None):
            out=self.produce(lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
        self.assertEqual(out["status"],"source_unavailable")
        self.assertFalse(snapshot_path(self.state_root,ASSIGNMENT,WAKE).exists())
    def test_s4_fence_blocks_fetch(self):
        self.authorize()
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",side_effect=PermissionError("unverified")):
            with self.assertRaises(PermissionError):
                self.produce(lambda _: (_ for _ in ()).throw(AssertionError("unexpected fetch")))
    def test_expired_active_lease_can_resume_same_authorized_work(self):
        self.authorize()
        self.expire_lease()
        self.assertEqual(self.capsule()["wake_intent"]["mode"], "resume")
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",return_value=None):
            out=self.produce()
        self.assertEqual(out["status"],"materialized")

    def test_active_unexpired_lease_cannot_trigger_duplicate_scan(self):
        self.authorize()
        lifecycle=EmployeeLifecycle(self.runtime)
        lifecycle.claim(ASSIGNMENT,EMPLOYEE,"live-lease")
        called=[]
        # A stale original wake is not a new authority for a concurrent fetch.
        stale={"employee_id":EMPLOYEE,"assignment_id":ASSIGNMENT,
               "wake_id":"wake_stale","presence_generation":1,"wake_intent":{}}
        with patch("agentos_node.hermes_metadata_feed._verify_delivery",return_value=None):
            with self.assertRaises(PermissionError):
                produce_snapshot(runtime_root=self.runtime.root,wake_root=self.wake_root,
                    state_root=self.state_root,capsule=stale,
                    fetch=lambda repo:called.append(repo))
        self.assertEqual(called,[])

    def test_network_sandbox_remains_intact(self):
        root=Path(__file__).resolve().parents[1]
        for name in [".agent/scripts/agentos-employee-worker-host-system.service",
                     ".agent/scripts/agentos-employee-worker-host.service"]:
            text=(root/name).read_text()
            self.assertIn("PrivateNetwork=true",text)

if __name__ == "__main__":
    unittest.main()
