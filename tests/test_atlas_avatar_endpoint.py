import unittest
from http.server import HTTPServer
from threading import Thread
import urllib.request
import json
from pathlib import Path

from agent_core.realm_server import RealmRequestHandler
from agent_core.realm_fabric import RealmFabricStore


class TestAtlasAvatarEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We start a lightweight local RealmRequestHandler server for testing
        fabric_path = Path("/home/ubuntu/agent-data/realm/fabric.json")
        fabric = RealmFabricStore(fabric_path)

        class MockRealmServer(HTTPServer):
            def __init__(self, server_address, RequestHandlerClass):
                self.fabric = fabric
                self.controller = None
                self.participants = None
                super().__init__(server_address, RequestHandlerClass)

        cls.httpd = MockRealmServer(("127.0.0.1", 0), RealmRequestHandler)
        cls.port = cls.httpd.server_port
        cls.thread = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_atlas_avatar_endpoint_returns_context(self):
        url = f"http://127.0.0.1:{self.port}/v1/atlas/avatar"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("schema"), "agentos.atlas-avatar-context/v1")
        self.assertFalse(data.get("credential_exposed"))
        
        # Verify avatar identity & guardrails
        avatar = data.get("avatar", {})
        self.assertEqual(avatar.get("role_id"), "system.atlas")
        self.assertIn("pitfalls_guardrails", avatar)
        self.assertIn("嚴禁靜默降級空殼", avatar["pitfalls_guardrails"])
        
        # Verify active selector & canonical IR
        selector = data.get("active_selector", {})
        self.assertIn("project_id", selector)
        self.assertIn("canonical_ir", data)


if __name__ == "__main__":
    unittest.main()
