import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.core_services import port_manager


class PortManagerGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Path(self.tmp.name) / "port_registry.json"
        self.patch = mock.patch.object(port_manager, "REGISTRY_FILE", self.registry)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_require_rejects_unregistered_port(self):
        with self.assertRaises(RuntimeError):
            port_manager.require_port(3000, "agentos-dashboard")

    def test_ensure_registers_then_require_accepts(self):
        port_manager.ensure_port(3000, "agentos-dashboard", "dashboard")
        self.assertEqual(port_manager.require_port(3000, "agentos-dashboard"), 3000)
        data=json.loads(self.registry.read_text())
        self.assertEqual(data["3000"]["project"], "agentos-dashboard")
        self.assertEqual(data["3000"]["managed_by"], "manager://port")

    def test_require_rejects_wrong_owner(self):
        port_manager.ensure_port(3000, "agentos-dashboard")
        with self.assertRaises(RuntimeError):
            port_manager.require_port(3000, "other-service")

    def test_migrate_requires_expected_current_owner(self):
        port_manager.ensure_port(3000, "agentmanager")
        with self.assertRaises(RuntimeError):
            port_manager.migrate_port(3000, "wrong-owner", "agentos-dashboard")

    def test_migrate_records_transfer(self):
        port_manager.ensure_port(3000, "agentmanager", "Dashboard Next.js")
        port_manager.migrate_port(3000, "agentmanager", "agentos-dashboard", "AgentOS Dashboard / Realm Gateway")
        data=json.loads(self.registry.read_text())
        self.assertEqual(data["3000"]["project"], "agentos-dashboard")
        self.assertEqual(data["3000"]["migration"]["from_project"], "agentmanager")
        self.assertEqual(data["3000"]["migration"]["to_project"], "agentos-dashboard")


if __name__ == "__main__":
    unittest.main()
