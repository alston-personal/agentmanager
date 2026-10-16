import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from agent_core.control_plane import ControlPlaneStore
from agent_core.bounty_pdca_wake import run_bounty_pdca_wake


class BountyWakeIntegrationTests(unittest.TestCase):
    def test_leased_plan_wake_persists_result(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            payload = {"cycle":{"issue":None,"stage":"PLAN","revision":0,"last_event":"initialized"},
                       "event":{"type":"CANDIDATE_SELECTED","issue":"Parabola#16"}}
            store.submit_task("bounty.pdca.wake", payload, "wake:plan:one")
            task = store.lease_next_task("worker-1", ["bounty.pdca.wake"])
            receipt = run_bounty_pdca_wake(store,task,node_id="worker-1")
            self.assertEqual(receipt["result"]["stage"],"DO")
            self.assertEqual(receipt["result"]["issue"],"Parabola#16")
            self.assertFalse(receipt["result"]["bountyPaid"])

    def test_wrong_worker_cannot_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            payload={"cycle":{"issue":None,"stage":"PLAN"},"event":{"type":"CANDIDATE_SELECTED","issue":"x/y#1"}}
            store.submit_task("bounty.pdca.wake",payload,"wake:plan:two")
            task=store.lease_next_task("worker-1",["bounty.pdca.wake"])
            with self.assertRaises(ValueError):
                run_bounty_pdca_wake(store,task,node_id="worker-2")

    def test_lease_handover_cannot_commit_stale_result(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            payload={"cycle":{"issue":None,"stage":"PLAN"},"event":{"type":"CANDIDATE_SELECTED","issue":"x/y#1"}}
            store.submit_task("bounty.pdca.wake",payload,"wake:handover")
            task=store.lease_next_task("worker-1",["bounty.pdca.wake"])
            from agent_core import bounty_pdca_wake as module
            original=module.advance_bounty_cycle
            def reassign_during_compute(*args):
                with store._connect() as db:
                    db.execute("UPDATE tasks SET target_node_id=? WHERE task_id=?", ("worker-2", task["taskId"]))
                return original(*args)
            with patch.object(module,"advance_bounty_cycle",side_effect=reassign_during_compute):
                with self.assertRaises(ValueError):
                    run_bounty_pdca_wake(store,task,node_id="worker-1")
            with store._connect() as db:
                row=db.execute("SELECT status,target_node_id FROM tasks WHERE task_id=?",(task["taskId"],)).fetchone()
                self.assertEqual(row["status"],"leased")
                self.assertEqual(row["target_node_id"],"worker-2")


if __name__ == "__main__":
    unittest.main()
