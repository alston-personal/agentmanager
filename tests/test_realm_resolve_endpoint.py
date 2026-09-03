import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer


class TestRealmResolveEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        registry = NodeRegistry(path=root / "nodes.json")
        self.fabric = RealmFabricStore(path=root / "fabric.json", node_registry=registry)
        self.fabric.initialize_realm("realm-test")
        self.server = RealmHTTPServer(("127.0.0.1", 0), self.fabric)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def _post(self, body: dict, token: str | None = None):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(self.base_url + "/v1/resolve", data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=3) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _enroll(self):
        invite = self.fabric.create_invite(expires_minutes=5, label="chatgpt-web-test")
        manifest = {
            "schema": "agentos.node-manifest/v0.1",
            "realm_id": "realm-test",
            "node_id": "chatgpt-web-test",
            "role": "client",
            "hostname": "chatgpt-web",
            "platform": "web",
            "platform_release": "test",
            "capabilities": ["cognition.interactive"],
            "tool_presence": {},
            "surface_inventory": {"surfaces": [{"provider": "chatgpt-web", "kind": "chat"}]},
        }
        return self.fabric.enroll(invite_id=invite["invite_id"], code=invite["code"], manifest=manifest)

    def test_resolve_requires_bearer_credential(self):
        status, payload = self._post({"schema": "agentos.resolve-request/v1", "node_id": "chatgpt-web-test", "intent": "continue", "project": "metashield-protocol"})
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])

    def test_enrolled_node_can_resolve_through_one(self):
        enrolled = self._enroll()
        expected = {
            "schema": "agentos.resolve/v1", "intent": "continue",
            "project": {"id": "metashield-protocol", "aliases": ["chamber", "echo"]},
            "active_goal": "continue closed beta",
            "execution_head": {"schema": "agentos.execution-head/v1", "branch": "develop"},
            "continuation": {"goal": "continue closed beta"},
            "node_context": {"node_id": "chatgpt-web-test"}, "next_action": "continue", "availability": {}, "provenance": {},
        }
        with patch("agent_core.realm_server.bootstrap_snapshot", return_value={"node_id": "chatgpt-web-test"}), patch("agent_core.realm_server.resolve_continuation", return_value=expected) as resolver:
            status, payload = self._post({"schema": "agentos.resolve-request/v1", "node_id": "chatgpt-web-test", "intent": "continue", "project": "metashield-protocol"}, token=enrolled["node_token"])
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema"], "agentos.resolve/v1")
        self.assertEqual(payload["project"]["id"], "metashield-protocol")
        resolver.assert_called_once_with("metashield-protocol", node_context={"node_id": "chatgpt-web-test"})

    def test_enrolled_node_can_resolve_active_continuation(self):
        enrolled = self._enroll()
        active = {
            "selector": {
                "schema": "agentos.active-continuation/v1",
                "project_id": "agentos-core",
                "index_id": "idx-active",
                "ir_id": "ir-active",
            },
            "resolution": {
                "schema": "agentos.resolve/v1",
                "intent": "continue",
                "project": {"id": "agentos-core"},
                "execution_head": {"index_id": "idx-active"},
                "continuation": {
                    "canonical_ir": {
                        "schema_version": "agentos.ir/v1",
                        "index_id": "idx-active",
                        "ir_id": "ir-active",
                    }
                },
            },
        }
        with patch(
            "agent_core.realm_server.bootstrap_snapshot",
            return_value={"node_id": "chatgpt-web-test"},
        ), patch(
            "agent_core.realm_server.resolve_active_continuation",
            return_value=active,
        ) as resolver:
            status, payload = self._post(
                {
                    "schema": "agentos.resolve-request/v1",
                    "node_id": "chatgpt-web-test",
                    "intent": "continue",
                    "selection": "active",
                },
                token=enrolled["node_token"],
            )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["selection_source"], "ONE_ACTIVE_CONTINUATION")
        self.assertEqual(payload["active_selector"]["ir_id"], "ir-active")
        self.assertEqual(payload["node_context"]["node_id"], "chatgpt-web-test")
        resolver.assert_called_once_with()

    def test_wrong_node_token_is_rejected_before_resolver(self):
        self._enroll()
        with patch("agent_core.realm_server.resolve_continuation") as resolver:
            status, payload = self._post({"schema": "agentos.resolve-request/v1", "node_id": "chatgpt-web-test", "intent": "continue", "project": "metashield-protocol"}, token="wrong-token")
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])
        resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
