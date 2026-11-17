import unittest
import os
import json
from pathlib import Path
from agent_core.role_handoff_bus import (
    dispatch_task,
    acknowledge_tasks_for_role,
    get_prioritized_queue_for_role,
    complete_handoff_task,
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

if __name__ == "__main__":
    unittest.main()
