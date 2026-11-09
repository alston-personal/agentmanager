from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_core.employee_lifecycle import EmployeeLifecycle
from agent_core.employee_runtime import EmployeeRuntime
from agent_core.employee_threads import (
    THREAD_LINK_SCHEMA,
    THREAD_RETURN_SCHEMA,
    EmployeeThreadService,
)


T0 = datetime(2026, 9, 2, 6, 0, 0, tzinfo=timezone.utc)


class EmployeeThreadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime = EmployeeRuntime(self.root)
        self.runtime.create_employee("spec-steward", "Spec Steward")
        self.runtime.create_employee("weaver", "Weaver")
        self.runtime.create_assignment(
            "parent-1",
            "spec-steward",
            "Close specification gaps",
            thread_head="ir-parent-0",
        )
        self.lifecycle = EmployeeLifecycle(self.runtime)
        self.lifecycle.claim(
            "parent-1",
            "spec-steward",
            "parent-lease",
            lease_seconds=300,
            now=T0,
        )
        self.threads = EmployeeThreadService(self.lifecycle)

    def tearDown(self):
        self.tmp.cleanup()

    def _spawn_and_finish_child(self):
        link = self.threads.spawn_child(
            "parent-1",
            "parent-lease",
            "child-1",
            "weaver",
            "Resolve one bounded specification question",
            constraints=["no-parent-overwrite"],
            thread_head="ir-child-0",
            now=T0 + timedelta(seconds=5),
        )
        self.lifecycle.claim(
            "child-1",
            "weaver",
            "child-lease",
            now=T0 + timedelta(seconds=10),
        )
        self.lifecycle.checkpoint(
            "child-1",
            "child-lease",
            "ir-child-complete",
            now=T0 + timedelta(seconds=20),
        )
        receipt = self.lifecycle.finish(
            "child-1",
            "child-lease",
            result_summary={
                "answer": "bounded",
                "private_detail": "must-not-be-in-return-envelope",
            },
            now=T0 + timedelta(seconds=30),
        )
        return link, receipt

    def test_spawn_child_captures_parent_head_and_parent_relation(self):
        link = self.threads.spawn_child(
            "parent-1",
            "parent-lease",
            "child-1",
            "weaver",
            "Resolve one bounded specification question",
            now=T0 + timedelta(seconds=5),
        )
        self.assertEqual(link.schema, THREAD_LINK_SCHEMA)
        self.assertEqual(link.parent_thread_head_at_spawn, "ir-parent-0")
        child = self.runtime.get_assignment("child-1")
        self.assertEqual(child.parent_assignment_id, "parent-1")
        self.assertEqual(child.employee_id, "weaver")

    def test_child_completion_prepares_bounded_return_without_mutating_parent(self):
        _, receipt = self._spawn_and_finish_child()
        envelope = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        self.assertEqual(envelope.schema, THREAD_RETURN_SCHEMA)
        self.assertEqual(envelope.child_outcome, "completed")
        self.assertEqual(envelope.child_thread_head, "ir-child-complete")
        self.assertEqual(envelope.child_receipt_generation, receipt.generation)
        self.assertEqual(envelope.parent_thread_head_current, "ir-parent-0")
        self.assertFalse(envelope.parent_changed_since_spawn)
        self.assertTrue(envelope.apply_authority_required)
        self.assertEqual(
            self.runtime.get_assignment("parent-1").thread_head,
            "ir-parent-0",
        )
        serialized = json.dumps(envelope.__dict__ if hasattr(envelope, "__dict__") else {
            "schema": envelope.schema,
            "child_outcome": envelope.child_outcome,
            "child_thread_head": envelope.child_thread_head,
            "parent_thread_head_current": envelope.parent_thread_head_current,
        }, ensure_ascii=False)
        self.assertNotIn("private_detail", serialized)
        self.assertNotIn("must-not-be-in-return-envelope", serialized)

    def test_parent_progress_after_spawn_is_reported_not_overwritten(self):
        self._spawn_and_finish_child()
        self.lifecycle.checkpoint(
            "parent-1",
            "parent-lease",
            "ir-parent-parallel-progress",
            now=T0 + timedelta(seconds=35),
        )
        envelope = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        self.assertTrue(envelope.parent_changed_since_spawn)
        self.assertEqual(
            envelope.parent_thread_head_at_spawn, "ir-parent-0"
        )
        self.assertEqual(
            envelope.parent_thread_head_current,
            "ir-parent-parallel-progress",
        )

    def test_apply_return_requires_live_parent_lease_and_exact_head_fence(self):
        self._spawn_and_finish_child()
        envelope = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        link = self.threads.apply_return(
            "parent-1",
            "parent-lease",
            "child-1",
            expected_parent_thread_head=envelope.parent_thread_head_current,
            new_parent_thread_head="ir-parent-with-child",
            now=T0 + timedelta(seconds=50),
        )
        self.assertEqual(link.status, "applied")
        self.assertEqual(link.applied_parent_thread_head, "ir-parent-with-child")
        self.assertEqual(
            self.runtime.get_assignment("parent-1").thread_head,
            "ir-parent-with-child",
        )

    def test_stale_prepared_return_cannot_overwrite_newer_parent_head(self):
        self._spawn_and_finish_child()
        envelope = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        self.lifecycle.checkpoint(
            "parent-1",
            "parent-lease",
            "ir-parent-newer",
            now=T0 + timedelta(seconds=45),
        )
        with self.assertRaisesRegex(
            RuntimeError, "parent_thread_advanced_after_return_preparation"
        ):
            self.threads.apply_return(
                "parent-1",
                "parent-lease",
                "child-1",
                expected_parent_thread_head=envelope.parent_thread_head_current,
                new_parent_thread_head="ir-unsafe-overwrite",
                now=T0 + timedelta(seconds=50),
            )
        self.assertEqual(
            self.runtime.get_assignment("parent-1").thread_head,
            "ir-parent-newer",
        )

    def test_apply_return_rejects_expired_parent_owner(self):
        self._spawn_and_finish_child()
        envelope = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        with self.assertRaisesRegex(RuntimeError, "lease_expired"):
            self.threads.apply_return(
                "parent-1",
                "parent-lease",
                "child-1",
                expected_parent_thread_head=envelope.parent_thread_head_current,
                new_parent_thread_head="ir-parent-with-child",
                now=T0 + timedelta(seconds=301),
            )

    def test_child_must_have_terminal_receipt_before_return(self):
        self.threads.spawn_child(
            "parent-1",
            "parent-lease",
            "child-1",
            "weaver",
            "Still working",
            now=T0 + timedelta(seconds=5),
        )
        with self.assertRaisesRegex(
            RuntimeError, "child_assignment_not_returnable"
        ):
            self.threads.prepare_return(
                "child-1", now=T0 + timedelta(seconds=10)
            )

    def test_return_state_survives_runtime_restart(self):
        self._spawn_and_finish_child()
        prepared = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        restarted_runtime = EmployeeRuntime(self.root)
        restarted_lifecycle = EmployeeLifecycle(restarted_runtime)
        restarted_threads = EmployeeThreadService(restarted_lifecycle)
        loaded = restarted_threads.get_return("child-1")
        self.assertEqual(loaded.return_id, prepared.return_id)
        self.assertEqual(loaded.child_thread_head, "ir-child-complete")
        self.assertEqual(
            restarted_threads.get_link("child-1").status,
            "return_ready",
        )

    def test_duplicate_apply_is_idempotent_for_same_new_head(self):
        self._spawn_and_finish_child()
        envelope = self.threads.prepare_return(
            "child-1", now=T0 + timedelta(seconds=40)
        )
        first = self.threads.apply_return(
            "parent-1",
            "parent-lease",
            "child-1",
            expected_parent_thread_head=envelope.parent_thread_head_current,
            new_parent_thread_head="ir-parent-with-child",
            now=T0 + timedelta(seconds=50),
        )
        second = self.threads.apply_return(
            "parent-1",
            "parent-lease",
            "child-1",
            expected_parent_thread_head=envelope.parent_thread_head_current,
            new_parent_thread_head="ir-parent-with-child",
            now=T0 + timedelta(seconds=60),
        )
        self.assertEqual(first.link_id, second.link_id)
        self.assertEqual(second.status, "applied")


if __name__ == "__main__":
    unittest.main()
