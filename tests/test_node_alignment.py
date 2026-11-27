"""Unit tests for Node Alignment Engine & Skill."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from agent_core.node_alignment import NodeAlignmentEngine, _utc_now


class TestNodeAlignmentEngine(unittest.TestCase):
    def setUp(self):
        self.mock_fabric = MagicMock()
        self.engine = NodeAlignmentEngine(fabric_store=self.mock_fabric)

    def test_audit_all_nodes_live_and_stale(self):
        now = datetime.now(timezone.utc)
        live_time = (now - timedelta(seconds=10)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        stale_time = (now - timedelta(seconds=600)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        self.mock_fabric.load.return_value = {
            "schema": "agentos.realm-fabric/v0.1",
            "nodes": {
                "vopc5750": {
                    "last_seen_at": live_time,
                    "platform": "windows",
                    "capabilities": ["desktop.open_url"],
                    "token_hash": "abc123hash",
                },
                "dqa03backup": {
                    "last_seen_at": stale_time,
                    "platform": "linux",
                    "capabilities": ["filesystem.read"],
                    "token_hash": "def456hash",
                },
                "retired-node": {
                    "last_seen_at": None,
                    "platform": "unknown",
                    "capabilities": [],
                    "token_hash": None,
                },
            },
        }

        report = self.engine.audit_all_nodes(max_stale_seconds=300)

        self.assertEqual(report["schema"], "agentos.node-alignment-receipt/v1")
        self.assertEqual(report["total_nodes"], 3)
        self.assertEqual(report["summary"]["live"], 1)
        self.assertEqual(report["summary"]["stale"], 1)
        self.assertEqual(report["summary"]["offline"], 1)

        self.assertEqual(report["nodes"]["vopc5750"]["status"], "live")
        self.assertEqual(report["nodes"]["vopc5750"]["platform_type"], "windows")
        self.assertTrue(report["nodes"]["vopc5750"]["token_registered"])

        self.assertEqual(report["nodes"]["dqa03backup"]["status"], "stale")
        self.assertEqual(report["nodes"]["retired-node"]["status"], "offline")

        # Anomaly verification
        self.assertEqual(len(report["anomalies"]), 2)
        anomaly_kinds = [a["kind"] for a in report["anomalies"]]
        self.assertIn("HEARTBEAT_STALE", anomaly_kinds)
        self.assertIn("NODE_OFFLINE", anomaly_kinds)

    def test_dispatch_surface_alignment_probe(self):
        self.mock_fabric.queue_task.return_value = {"ok": True, "task_id": "test-task"}
        res = self.engine.dispatch_surface_alignment_probe("vopc5750")

        self.mock_fabric.queue_task.assert_called_once()
        call_args = self.mock_fabric.queue_task.call_args[0]
        self.assertEqual(call_args[0], "vopc5750")
        task = call_args[1]
        self.assertEqual(task["action"], "agent.surface.inspect")
        self.assertEqual(task["schema"], "agentos.node-task/v0.1")
        self.assertEqual(res, {"ok": True, "task_id": "test-task"})


if __name__ == "__main__":
    unittest.main()
