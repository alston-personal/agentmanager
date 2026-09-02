from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.core_supervisor_service import CoreSupervisorService
from agent_core.core_work_items import WORK_ITEM_SCHEMA, WorkItemStore
from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime


T0 = datetime(2026, 9, 2, 5, 30, 0, tzinfo=timezone.utc)


class CoreSupervisorServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.runtime.create_employee(
            "spec-steward",
            "Spec Steward",
            role_ids=["governance.spec_steward"],
            skill_ids=["spec.audit"],
        )
        self.runtime.create_assignment(
            "audit-001",
            "spec-steward",
            "Audit closure gaps",
            thread_head="ir:start",
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)

    def tearDown(self):
        self.tmp.cleanup()

    def service(self, owner="supervisor-a"):
        return CoreSupervisorService(
            self.lifecycle,
            owner_id=owner,
            base_poll_seconds=2,
            max_poll_seconds=16,
        )

    def test_singleton_leader_rejects_competing_live_owner(self):
        a = self.service("supervisor-a")
        b = self.service("supervisor-b")
        lease = a.claim_leader(lease_seconds=30, now=T0)
        self.assertEqual(lease.generation, 1)
        with self.assertRaisesRegex(RuntimeError, "supervisor_leader_already_active"):
            b.claim_leader(lease_seconds=30, now=T0 + timedelta(seconds=5))

    def test_expired_leader_takeover_increments_generation_and_marks_unknown(self):
        a = self.service("supervisor-a")
        b = self.service("supervisor-b")
        a.claim_leader(lease_seconds=10, now=T0)
        takeover = b.claim_leader(lease_seconds=30, now=T0 + timedelta(seconds=11))
        self.assertEqual(takeover.generation, 2)
        self.assertEqual(takeover.prior_owner_state, "unknown")

    def test_cycle_persists_reconcile_intent_before_any_dispatch(self):
        service = self.service()
        leader = service.claim_leader(now=T0)
        receipt = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        self.assertEqual(receipt.new_intent_count, 1)
        self.assertFalse(receipt.dispatch_performed)
        intent_files = list(service.intents_dir.glob("reconcile_*.json"))
        self.assertEqual(len(intent_files), 1)
        stored = json.loads(intent_files[0].read_text(encoding="utf-8"))
        self.assertEqual(stored["state"], "planned")
        self.assertFalse(stored["dispatch_performed"])
        self.assertEqual(stored["intent"]["employee_id"], "spec-steward")
        self.assertEqual(self.runtime.get_assignment("audit-001").state, "pending")
        self.assertIsNone(self.lifecycle.get_lease("audit-001"))

    def test_restart_does_not_duplicate_same_planned_intent(self):
        first = self.service("supervisor-a")
        lease = first.claim_leader(now=T0)
        cycle1 = first.run_cycle(lease.generation, now=T0 + timedelta(seconds=1))
        self.assertEqual(cycle1.new_intent_count, 1)

        restarted = self.service("supervisor-a")
        renewed = restarted.claim_leader(now=T0 + timedelta(seconds=2))
        cycle2 = restarted.run_cycle(renewed.generation, now=T0 + timedelta(seconds=3))
        self.assertEqual(cycle2.new_intent_count, 0)
        self.assertEqual(cycle2.total_planned_intent_count, 1)

    def test_unchanged_cycles_back_off_without_busy_loop(self):
        service = self.service()
        leader = service.claim_leader(now=T0)
        first = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        second = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=2))
        third = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=3))
        self.assertEqual(first.next_poll_seconds, 2)
        self.assertGreaterEqual(second.next_poll_seconds, 2)
        self.assertGreaterEqual(third.next_poll_seconds, second.next_poll_seconds)
        self.assertLessEqual(third.next_poll_seconds, 16)

    def test_work_item_dependency_blocks_assignment_until_explicit_completion(self):
        # Replace the ad-hoc assignment with a WorkItem-owned one so S3 can derive
        # blocked assignment ids from durable dependency state.
        self.runtime.update_assignment("audit-001", state="cancelled")
        store = WorkItemStore(self.runtime)
        store.persist({
            "schema": WORK_ITEM_SCHEMA,
            "work_item_id": "work-audit-002",
            "source_kind": "github_issue",
            "source_ref": "github:alston-personal/agentmanager#200",
            "project_id": "agentos-core",
            "employee_id": "spec-steward",
            "assignment_id": "audit-002",
            "goal": "Audit after dependency closes",
            "dependency_refs": ["github:alston-personal/agentmanager#197"],
            "state": "open",
        })
        store.project_pending_assignment("work-audit-002")
        service = self.service()
        leader = service.claim_leader(now=T0)
        blocked = service.run_cycle(leader.generation, dependency_states={}, now=T0 + timedelta(seconds=1))
        self.assertEqual(blocked.new_intent_count, 0)
        self.assertEqual(blocked.blocked_assignment_count, 1)

        ready = service.run_cycle(
            leader.generation,
            dependency_states={"github:alston-personal/agentmanager#197": "completed"},
            now=T0 + timedelta(seconds=2),
        )
        self.assertEqual(ready.new_intent_count, 1)
        self.assertEqual(ready.blocked_assignment_count, 0)

    def test_expired_assignment_is_journaled_as_resume_unknown(self):
        self.lifecycle.claim(
            "audit-001", "spec-steward", "lease-old", lease_seconds=30, now=T0
        )
        self.lifecycle.checkpoint(
            "audit-001", "lease-old", "ir:checkpoint", now=T0 + timedelta(seconds=10)
        )
        service = self.service()
        leader = service.claim_leader(lease_seconds=60, now=T0)
        receipt = service.run_cycle(leader.generation, now=T0 + timedelta(seconds=31))
        self.assertEqual(receipt.new_intent_count, 1)
        record = json.loads(next(service.intents_dir.glob("reconcile_*.json")).read_text(encoding="utf-8"))
        wake = record["intent"]["wake_intent"]
        self.assertTrue(wake["resume_required"])
        self.assertEqual(wake["prior_execution_state"], "unknown")
        self.assertEqual(wake["thread_head"], "ir:checkpoint")

    def test_cycle_requires_current_leader_ownership(self):
        service = self.service("supervisor-a")
        service.claim_leader(lease_seconds=10, now=T0)
        with self.assertRaisesRegex(RuntimeError, "supervisor_leader_expired"):
            service.run_cycle(1, now=T0 + timedelta(seconds=11))

    def test_health_projection_is_read_only_and_exposes_no_execution_claim(self):
        service = self.service()
        leader = service.claim_leader(now=T0)
        service.run_cycle(leader.generation, now=T0 + timedelta(seconds=1))
        health = service.health(now=T0 + timedelta(seconds=2))
        self.assertEqual(health["status"], "running")
        self.assertTrue(health["leader_live"])
        self.assertEqual(health["planned_intent_count"], 1)
        self.assertFalse(health["dispatch_performed"])


if __name__ == "__main__":
    unittest.main()
