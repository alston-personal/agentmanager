import unittest
import json
import tempfile
from pathlib import Path
from agentos_node.inspector import NodeInspector
from agent_core.control_plane import ControlPlaneStore

class TestNodeRuntime(unittest.TestCase):

    def test_inspector_payload(self):
        inspector = NodeInspector(device_alias="test-node-01")
        payload = inspector.harvest_payload()
        self.assertEqual(payload["device_alias"], "test-node-01")
        self.assertEqual(payload["protocol"], "ancp")
        self.assertEqual(payload["messageType"], "node.harvest_report")
        self.assertIn("has_secrets", payload["secrets_info"])

    def test_control_plane_harvest_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ControlPlaneStore(db_path=Path(tmpdir) / "test.sqlite3")
            inspector = NodeInspector(device_alias="test-node-record")
            payload = inspector.harvest_payload()
            res = store.record_harvest_report(payload)
            self.assertEqual(res["deviceAlias"], "test-node-record")
            self.assertTrue(Path(res["savedTo"]).exists())

if __name__ == "__main__":
    unittest.main()
