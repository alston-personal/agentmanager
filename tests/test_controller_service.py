import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib import error, request

from agent_core.controller_service import ControllerService
from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer


class ControllerFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        registry = NodeRegistry(path=root / 'nodes.json')
        self.fabric = RealmFabricStore(path=root / 'fabric.json', node_registry=registry)
        self.fabric.initialize_realm('realm-test')
        manifest = {
            'schema': 'agentos.node-manifest/v0.1',
            'realm_id': 'realm-test',
            'node_id': 'vopc5750',
            'role': 'client',
            'hostname': 'VOPC5750',
            'platform': 'Windows',
            'platform_release': '11',
            'capabilities': ['agent.surface.inspect'],
            'tool_presence': {},
            'surface_inventory': {'surfaces': []},
        }
        invite = self.fabric.create_invite(expires_minutes=5, label='controller-test')
        enrolled = self.fabric.enroll(invite_id=invite['invite_id'], code=invite['code'], manifest=manifest)
        self.node_token = enrolled['node_token']
        self.fabric.record_heartbeat({
            'schema': 'agentos.node-heartbeat/v0.1',
            'realm_id': 'realm-test',
            'node_id': 'vopc5750',
            'status': 'online',
            'observed_at': None,
            'uptime_seconds': 10,
            'surface_count': 0,
            'manifest': manifest,
        }, self.node_token)

    def tearDown(self):
        self.tmp.cleanup()


class TestControllerService(ControllerFixture):
    def test_surface_inspect_enters_controller_and_queues_existing_node_task(self):
        result = ControllerService(self.fabric).dispatch({
            'schema': 'agentos.controller-dispatch/v0.1',
            'node_id': 'vopc5750',
            'action': 'agent.surface.inspect',
            'payload': {},
        })
        self.assertTrue(result['ok'])
        self.assertTrue(result['controller_entered'])
        self.assertEqual(result['node_id'], 'vopc5750')
        self.assertEqual(result['action'], 'agent.surface.inspect')
        tasks = self.fabric.load()['tasks']['vopc5750']
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['schema'], 'agentos.node-task/v0.1')
        self.assertEqual(tasks[0]['action'], 'agent.surface.inspect')
        self.assertEqual(tasks[0]['task_id'], result['task_id'])

    def test_unadvertised_capability_is_rejected_before_queue(self):
        with self.assertRaisesRegex(ValueError, 'does not advertise capability'):
            ControllerService(self.fabric).dispatch({'node_id': 'vopc5750', 'action': 'desktop.open_url'})
        self.assertEqual(self.fabric.load()['tasks']['vopc5750'], [])


class TestControllerEndpoint(ControllerFixture):
    def setUp(self):
        super().setUp()
        self.server = RealmHTTPServer(('127.0.0.1', 0), self.fabric)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        super().tearDown()

    def test_controller_dispatch_http_route_enters_service(self):
        req = request.Request(
            self.base_url + '/v1/controller/dispatch',
            data=json.dumps({'schema': 'agentos.controller-dispatch/v0.1', 'node_id': 'vopc5750', 'action': 'agent.surface.inspect'}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with request.urlopen(req, timeout=3) as resp:
                status = resp.status
                body = json.loads(resp.read().decode('utf-8'))
        except error.HTTPError as exc:
            status = exc.code
            body = json.loads(exc.read().decode('utf-8'))
        self.assertEqual(status, 200, body)
        self.assertTrue(body['controller_entered'])
        self.assertEqual(body['action'], 'agent.surface.inspect')
        self.assertEqual(self.fabric.load()['tasks']['vopc5750'][0]['task_id'], body['task_id'])


if __name__ == '__main__':
    unittest.main()
