from __future__ import annotations

import unittest

from agentos_node.bootstrap_scheduler import _select_external_capability_candidate


class ExternalCapabilityCandidateTests(unittest.TestCase):
    def test_selects_freshest_online_capable_external_node(self) -> None:
        nodes = [
            {
                "node_id": "oracle-core-node",
                "role": "core",
                "status": "online",
                "heartbeat_age_seconds": 0,
                "capabilities": ["threads.gui.read"],
            },
            {
                "node_id": "oracle-exec",
                "role": "client",
                "status": "online",
                "heartbeat_age_seconds": 1,
                "capabilities": ["threads.gui.read"],
            },
            {
                "node_id": "mbpr",
                "role": "client",
                "status": "online",
                "heartbeat_age_seconds": 9,
                "capabilities": ["threads.gui.read", "shell.exec"],
            },
            {
                "node_id": "vopc5750",
                "role": "client",
                "status": "online",
                "heartbeat_age_seconds": 3,
                "capabilities": ["threads.gui.read", "shell.exec"],
            },
        ]

        node, reason = _select_external_capability_candidate(nodes, ("threads.gui.read",))

        self.assertEqual(reason, "ready")
        self.assertIsNotNone(node)
        self.assertEqual(node["node_id"], "vopc5750")

    def test_reports_offline_when_external_nodes_exist_but_none_are_online(self) -> None:
        nodes = [
            {
                "node_id": "mbpr",
                "role": "client",
                "status": "offline",
                "heartbeat_age_seconds": 90,
                "capabilities": ["threads.gui.read"],
            }
        ]

        node, reason = _select_external_capability_candidate(nodes, ("threads.gui.read",))

        self.assertIsNone(node)
        self.assertEqual(reason, "external_nodes_offline")

    def test_reports_capability_gap_when_online_nodes_do_not_match(self) -> None:
        nodes = [
            {
                "node_id": "vopc5750",
                "role": "client",
                "status": "online",
                "heartbeat_age_seconds": 2,
                "capabilities": ["desktop.open_url", "shell.exec"],
            }
        ]

        node, reason = _select_external_capability_candidate(nodes, ("threads.gui.read",))

        self.assertIsNone(node)
        self.assertEqual(reason, "external_nodes_missing_capability")

    def test_local_oracle_nodes_do_not_count_as_external_fallback(self) -> None:
        nodes = [
            {
                "node_id": "oracle-core-node",
                "role": "core",
                "status": "online",
                "heartbeat_age_seconds": 0,
                "capabilities": ["threads.gui.read"],
            },
            {
                "node_id": "oracle-exec",
                "role": "client",
                "status": "online",
                "heartbeat_age_seconds": 0,
                "capabilities": ["threads.gui.read"],
            },
        ]

        node, reason = _select_external_capability_candidate(nodes, ("threads.gui.read",))

        self.assertIsNone(node)
        self.assertEqual(reason, "external_nodes_not_registered")


if __name__ == "__main__":
    unittest.main()
