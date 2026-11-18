import unittest
import os
import json
from pathlib import Path
from agent_core.role_handoff_bus import (
    dispatch_task,
    acknowledge_tasks_for_role,
    get_prioritized_queue_for_role,
    complete_handoff_task,
    update_task_progress,
    get_task_progress,
    HANDOFF_BUS_FILE
)

class RoleHandoffBusTests(unittest.TestCase):
    def setUp(self):
        if HANDOFF_BUS_FILE.exists():
            HANDOFF_BUS_FILE.unlink()

    def tearDown(self):
        if HANDOFF_BUS_FILE.exists():
            HANDOFF_BUS_FILE.unlink()

    def test_handoff_ack_and_priority_queue(self):
        # 1. Dispatch low priority and high priority tasks
        t_low = dispatch_task(
            source_role="sector.weaver",
            target_role="sector.paw",
            title="低優先級待辦",
            payload={"action": "cleanup"},
            priority="P8",
            priority_weight=20,
            task_id="task-low"
        )
        t_high = dispatch_task(
            source_role="sector.weaver",
            target_role="sector.paw",
            title="緊急安全性修復",
            payload={"action": "security_fix"},
            priority="P0",
            priority_weight=100,
            task_id="task-high"
        )
        self.assertEqual(t_low["status"], "DISPATCHED")
        self.assertEqual(t_high["status"], "DISPATCHED")

        # 2. Target role acknowledges tasks
        acked = acknowledge_tasks_for_role("the-paw")
        self.assertEqual(len(acked), 2)
        for a in acked:
            self.assertEqual(a["status"], "ACKNOWLEDGED")
            self.assertIsNotNone(a["ack_receipt"])
            self.assertEqual(a["ack_receipt"]["received_by"], "the-paw")

        # 3. Retrieve prioritized queue (P0 must be first)
        queue = get_prioritized_queue_for_role("the-paw")
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["task_id"], "task-high")
        self.assertEqual(queue[1]["task_id"], "task-low")

        # 4. Complete top task
        ok = complete_handoff_task("task-high", "the-paw", "PASS", {"commit": "patch123"})
        self.assertTrue(ok)

        # 5. Remaining queue has only low task
        rem = get_prioritized_queue_for_role("the-paw")
        self.assertEqual(len(rem), 1)
        self.assertEqual(rem[0]["task_id"], "task-low")

    def test_progress_tick_and_auto_callback(self):
        # 1. Dispatch task with explicit callback target and caller context
        task = dispatch_task(
            source_role="executor.antigravity",
            target_role="runtime.worker",
            title="測試代碼編譯與生成",
            payload={"action": "build_package"},
            priority="P2",
            task_id="task-build-001",
            callback={
                "target_role": "executor.antigravity",
                "intent": "deploy_after_build",
                "context": {"source_branch": "feat/my-feature", "version": "v1.0"}
            }
        )
        self.assertEqual(task["status"], "DISPATCHED")

        # 2. Worker updates progress ticks
        self.assertTrue(update_task_progress("task-build-001", "RUNNING_TESTS", 50, "Executing unit tests", updated_by="runtime.worker"))
        
        # 3. Executor queries task progress
        prog = get_task_progress("task-build-001")
        self.assertIsNotNone(prog)
        self.assertEqual(prog["status"], "IN_PROGRESS")
        self.assertEqual(prog["progress"]["percent"], 50)
        self.assertEqual(prog["progress"]["stage"], "RUNNING_TESTS")

        # 4. Worker completes task -> Auto callback should trigger
        ok = complete_handoff_task(
            task_id="task-build-001",
            completing_role="runtime.worker",
            verdict="PASS",
            details={"artifacts": ["dist/package.tar.gz"]}
        )
        self.assertTrue(ok)

        # 5. Verify task is COMPLETED and execution-receipt is attached
        prog_done = get_task_progress("task-build-001")
        self.assertEqual(prog_done["status"], "COMPLETED")
        self.assertEqual(prog_done["progress"]["percent"], 100)
        receipt = prog_done["completed_receipt"]
        self.assertEqual(receipt["schema"], "agentos.execution-receipt/v1")
        self.assertEqual(receipt["verdict"], "PASS")

        # 6. Verify Executor received auto-callback task in its queue
        ack_cb = acknowledge_tasks_for_role("executor.antigravity")
        self.assertEqual(len(ack_cb), 1)
        cb_task = ack_cb[0]
        self.assertEqual(cb_task["source_role"], "runtime.worker")
        self.assertEqual(cb_task["target_role"], "executor.antigravity")
        self.assertEqual(cb_task["payload"]["intent"], "deploy_after_build")
        self.assertEqual(cb_task["payload"]["caller_context"]["source_branch"], "feat/my-feature")
        self.assertEqual(cb_task["payload"]["receipt"]["verdict"], "PASS")

if __name__ == "__main__":
    unittest.main()
