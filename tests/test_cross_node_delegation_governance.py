from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer
from agentos_node.thin_client import ThinClientPolicy
from agentos_node.thin_client_transport import ThinClientTransport, build_client


class TestCrossNodeDelegationGovernance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = NodeRegistry(self.root / 'nodes.json')
        self.fabric = RealmFabricStore(self.root / 'fabric.json', node_registry=self.registry)
        self.fabric.initialize_realm('realm-governed-test')
        self.server = RealmHTTPServer(('127.0.0.1', 0), self.fabric)
        self.port = self.server.server_address[1]
        self.base_url = f'http://127.0.0.1:{self.port}'

        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self.policy = ThinClientPolicy(
            allowed_executables={'python', 'python3'},
            readable_roots=(self.root,),
            writable_roots=(self.root,),
        )
        # Node A: Sender (e.g. dqa03backup)
        invite_a = self.fabric.create_invite(expires_minutes=5, label='dqa03backup')
        self.config_a = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite_a['invite_id'],
            code=invite_a['code'],
            node_id='dqa03backup',
            policy=self.policy,
            config_path=self.root / 'client_a.json',
        )
        self.client_a = build_client(self.config_a, self.policy)

        # Node B: Receiver (e.g. vopc5750)
        invite_b = self.fabric.create_invite(expires_minutes=5, label='vopc5750')
        self.config_b = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite_b['invite_id'],
            code=invite_b['code'],
            node_id='vopc5750',
            policy=self.policy,
            config_path=self.root / 'client_b.json',
        )
        self.client_b = build_client(self.config_b, self.policy)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_lateral_shell_exec_is_strictly_blocked(self):
        """Cross-node delegation must NEVER permit lateral shell.exec."""
        forbidden_task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-malicious-shell',
            'action': 'shell.exec',
            'executable': 'python3',
            'argv': ['-c', 'print("malicious lateral jump")'],
        }
        with self.assertRaises(Exception) as ctx:
            self.client_a.dispatch_task('vopc5750', forbidden_task)
        self.assertIn("strictly prohibited across nodes", str(ctx.exception))

    def test_invalid_action_is_blocked(self):
        """Actions not in the cross-node capability whitelist must be rejected."""
        unapproved_task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-unapproved-action',
            'action': 'arbitrary.dangerous_call',
        }
        with self.assertRaises(Exception) as ctx:
            self.client_a.dispatch_task('vopc5750', unapproved_task)
        self.assertIn("not in the allowed cross-node capability whitelist", str(ctx.exception))

    def test_governed_desktop_open_url_delegation_succeeds(self):
        """Governed desktop.open_url task passes validation, queues, and returns delegation schema."""
        open_url_task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-delegated-open-url',
            'action': 'desktop.open_url',
            'url': 'https://studio.milkcat.org/docs/litellm',
        }
        res = self.client_a.dispatch_task('vopc5750', open_url_task)
        self.assertTrue(res.get('ok'))
        delegation = res.get('delegation')
        self.assertEqual(delegation.get('schema'), 'agentos.cross-node-delegation/v1')
        self.assertEqual(delegation.get('caller_node_id'), 'dqa03backup')
        self.assertEqual(delegation.get('target_node_id'), 'vopc5750')
        self.assertEqual(delegation.get('action'), 'desktop.open_url')

        # Target node pulls the task cleanly
        tasks = self.client_b.pull_tasks(wait_seconds=1.0)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['task_id'], 'task-delegated-open-url')
        self.assertEqual(tasks[0]['url'], 'https://studio.milkcat.org/docs/litellm')

    def test_get_receipt_endpoint(self):
        """GET /v1/receipts and /v1/delegation/receipt cleanly retrieves archived receipts."""
        import urllib.request, json
        # Record a dummy receipt into fabric
        dummy_receipt = {
            'schema': 'agentos.node-receipt/v0.1',
            'realm_id': 'realm-governed-test',
            'node_id': 'vopc5750',
            'task_id': 'task-receipt-test-123',
            'action': 'desktop.open_url',
            'ok': True,
        }
        self.fabric.record_receipt(dummy_receipt, self.config_b.node_token)

        url = f'{self.base_url}/v1/delegation/receipt?task_id=task-receipt-test-123'
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {self.config_a.node_token}'})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get('ok'))
            self.assertEqual(data.get('receipt', {}).get('task_id'), 'task-receipt-test-123')
