import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.system_health_probe import check_ports_from_manager, check_node_heartbeats


class TestSystemHealthProbe(unittest.TestCase):
    def test_live_health_probe_passes_on_running_system(self):
        ports_ok, port_findings = check_ports_from_manager()
        nodes_ok, node_findings = check_node_heartbeats(max_idle_seconds=600)
        self.assertTrue(ports_ok, f"Ports probe failed: {port_findings}")
        self.assertTrue(nodes_ok, f"Node heartbeats failed: {node_findings}")

    @patch("scripts.system_health_probe.PORT_REGISTRY")
    def test_detects_port_registry_parsing_failure(self, mock_reg):
        mock_reg.is_file.return_value = True
        mock_reg.read_text.return_value = "{ invalid json"
        ok, findings = check_ports_from_manager()
        self.assertFalse(ok)
        self.assertTrue(any("Failed to parse port registry" in f for f in findings))


if __name__ == "__main__":
    unittest.main()
