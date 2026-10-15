import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error, request

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer
from agent_core.control_inbox_bridge import OneControllerClient, OneControllerError


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

    def test_wrong_node_token_is_rejected_before_resolver(self):
        self._enroll()
        with patch("agent_core.realm_server.resolve_continuation") as resolver:
            status, payload = self._post({"schema": "agentos.resolve-request/v1", "node_id": "chatgpt-web-test", "intent": "continue", "project": "metashield-protocol"}, token="wrong-token")
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])
        resolver.assert_not_called()

    def _get_active(self, suffix='', token='controller-test'):
        headers = {} if token is None else {'Authorization': f'Bearer {token}'}
        req = request.Request(self.base_url + '/v1/controller/continuation/active' + suffix, headers=headers)
        try:
            with request.urlopen(req, timeout=3) as response:
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                return response.status, json.loads(response.read())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _active(self):
        return {
            'selector': {'project_id': 'agentos-core', 'index_id': 'idx-1', 'ir_id': 'ir-1', 'reason': 'PRIVATE_REASON'},
            'resolution': {
                'schema': 'agentos.resolve/v1', 'project': {'id': 'agentos-core'},
                'execution_head': {'index_id': 'idx-1'},
                'continuation': {'canonical_ir': {
                    'schema_version': 'agentos.ir/v1', 'index_id': 'idx-1', 'ir_id': 'ir-1', 'goal': 'PRIVATE_GOAL'
                }},
                'private_path': '/private/path', 'token': 'PRIVATE_TOKEN',
            },
        }

    def test_private_and_identity_endpoints_require_auth_before_resolution(self):
        self.server.controller_token = 'controller-test'
        with patch('agent_core.realm_server.resolve_active_continuation') as resolver:
            for suffix in ('', '/identity'):
                for token in (None, 'wrong'):
                    self.assertEqual(self._get_active(suffix, token)[0], 401)
            resolver.assert_not_called()

    def test_active_identity_drops_private_state_and_private_read_preserves_ir(self):
        self.server.controller_token = 'controller-test'
        active = self._active()
        with patch('agent_core.realm_server.resolve_active_continuation', return_value=active):
            status, public = self._get_active('/identity')
            self.assertEqual(status, 200)
            self.assertNotIn('PRIVATE', json.dumps(public))
            self.assertFalse(public['identity']['hydration_complete'])
            status, private = self._get_active()
            self.assertEqual(status, 200)
            self.assertEqual(private['resolution']['continuation']['canonical_ir'], active['resolution']['continuation']['canonical_ir'])
            self.assertNotIn('PRIVATE_TOKEN', json.dumps(private))
            self.assertNotIn('/private/path', json.dumps(private))

    def test_unresolved_active_is_sanitized_and_query_override_is_rejected(self):
        self.server.controller_token = 'controller-test'
        with patch('agent_core.realm_server.resolve_active_continuation', side_effect=ValueError('/private/state PRIVATE_TOKEN')) as resolver:
            for suffix in ('', '/identity'):
                status, body = self._get_active(suffix)
                self.assertEqual(status, 409)
                self.assertEqual(body, {'ok': False, 'error': 'ONE_IR_HEAD_UNRESOLVED'})
            resolver.reset_mock()
            self.assertEqual(self._get_active('?project=other')[0], 400)
            resolver.assert_not_called()

    def test_private_read_refuses_truncated_or_redacted_canonical_ir(self):
        self.server.controller_token = 'controller-test'
        for change in ({'goal': 'x' * 513}, {'token': 'PRIVATE_TOKEN'}):
            active = self._active()
            active['resolution']['continuation']['canonical_ir'].update(change)
            with patch('agent_core.realm_server.resolve_active_continuation', return_value=active):
                self.assertEqual(self._get_active()[0], 409)

    def test_real_file_generation_through_http_client_then_stale_refusal(self):
        self.server.controller_token = 'controller-test'
        root = Path(self.tmp.name) / 'data'
        project_dir = root / 'projects' / 'agentos-core'
        (project_dir / 'continuity').mkdir(parents=True)
        (root / 'runtime').mkdir()
        active = self._active()
        pointer = {'schema': 'agentos.active-continuation/v1', **active['selector']}
        selector_file = root / 'runtime' / 'active-continuation.json'
        selector_file.write_text(json.dumps(pointer))
        head_file = project_dir / 'execution-head.json'
        head_file.write_text(json.dumps({'schema': 'agentos.execution-head/v1', 'index_id': 'idx-1'}))
        ir_file = project_dir / 'continuity' / 'latest.json'
        ir_file.write_text(json.dumps(active['resolution']['continuation']))
        files = (selector_file, head_file, ir_file)
        before = [path.read_bytes() for path in files]
        project = {'id': 'agentos-core', 'identity_source': 'test', 'integrity': {'complete': True}}
        client = OneControllerClient(self.base_url, 'controller-test')
        with patch.dict(os.environ, {'AGENT_DATA_ROOT': str(root)}), patch('agent_core.resolve_facade.resolve_project_identity', return_value=project):
            identity = client.inspect_continuation()
            self.assertEqual(identity['index_id'], 'idx-1')
            self.assertEqual(self._get_active()[0], 200)
            self.assertEqual(before, [path.read_bytes() for path in files])
            head_file.write_text(json.dumps({'schema': 'agentos.execution-head/v1', 'index_id': 'idx-2'}))
            with self.assertRaisesRegex(OneControllerError, '^one_continuation_http_409$'):
                client.inspect_continuation()


if __name__ == "__main__":
    unittest.main()
