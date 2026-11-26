from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer
from agentos_node.thin_client import ThinClientPolicy
from agentos_node.thin_client_transport import ThinClientTransport, build_client


class TestRealmTaskDispatchApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = NodeRegistry(self.root / 'nodes.json')
        self.fabric = RealmFabricStore(self.root / 'fabric.json', node_registry=self.registry)
        self.fabric.initialize_realm('realm-test')
        self.server = RealmHTTPServer(('127.0.0.1', 0), self.fabric)
        self.port = self.server.server_address[1]
        self.base_url = f'http://127.0.0.1:{self.port}'

        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        # Enroll Node A (dispatcher, e.g. vopc5750)
        self.policy = ThinClientPolicy(
            allowed_executables={'python', 'python3'},
            readable_roots=(self.root,),
            writable_roots=(self.root,),
        )
        invite_a = self.fabric.create_invite(expires_minutes=5, label='node-a')
        self.config_a = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite_a['invite_id'],
            code=invite_a['code'],
            node_id='node-a',
            policy=self.policy,
            config_path=self.root / 'client_a.json',
        )
        self.client_a = build_client(self.config_a, self.policy)

        # Enroll Node B (worker, e.g. dqa03restore)
        invite_b = self.fabric.create_invite(expires_minutes=5, label='node-b')
        self.config_b = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite_b['invite_id'],
            code=invite_b['code'],
            node_id='node-b',
            policy=self.policy,
            config_path=self.root / 'client_b.json',
        )
        self.client_b = build_client(self.config_b, self.policy)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_node_dispatches_task_to_another_node_via_api(self):
        task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-cross-node-001',
            'action': 'filesystem.write',
            'path': str(self.root / 'worker_output.txt'),
            'content_utf8': 'dispatched from node-a',
        }
        res = self.client_a.dispatch_task('node-b', task)
        self.assertTrue(res.get('ok'))
        self.assertEqual(res.get('queued', {}).get('task_id'), 'task-cross-node-001')

        # Node B pulls the task via runtime API with zero latency/no git pull
        tasks = self.client_b.pull_tasks(wait_seconds=1.0)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['task_id'], 'task-cross-node-001')
        self.assertEqual(tasks[0]['action'], 'filesystem.write')

        # Node B executes the leased task and submits receipt
        receipt = self.client_b.client.execute(tasks[0])
        self.client_b._persist_and_submit_receipt(receipt)
        self.assertTrue(receipt['ok'])
        self.assertEqual((self.root / 'worker_output.txt').read_text(encoding='utf-8'), 'dispatched from node-a')

        # Confirm queue is now cleared via receipt submission
        self.assertEqual(self.client_b.pull_tasks(wait_seconds=0.1), [])
