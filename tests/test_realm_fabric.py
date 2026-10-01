import json
import tempfile
import threading
import unittest
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore
from agent_core.realm_server import RealmHTTPServer, RealmRequestHandler
from agentos_node.thin_client import ThinClientPolicy
from agentos_node.thin_client_transport import ThinClientTransport, build_client


class TestRealmFabric(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        registry = NodeRegistry(path=root / 'nodes.json')
        self.fabric = RealmFabricStore(path=root / 'fabric.json', node_registry=registry)
        self.fabric.initialize_realm('realm-test')
        self.server = RealmHTTPServer(('127.0.0.1', 0), self.fabric)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.workspace = root / 'workspace'
        self.workspace.mkdir()
        self.config_path = root / 'client.json'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tmp.cleanup()

    def test_enroll_heartbeat_task_receipt(self):
        invite = self.fabric.create_invite(expires_minutes=5, label='first-node')
        policy = ThinClientPolicy(
            allowed_executables={'python', 'python3'},
            readable_roots=(self.workspace,),
            writable_roots=(self.workspace,),
        )
        config = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite['invite_id'],
            code=invite['code'],
            node_id='win-test-01',
            policy=policy,
            config_path=self.config_path,
        )
        self.assertEqual(config.realm_id, 'realm-test')
        self.assertTrue(self.config_path.exists())

        transport = build_client(config, policy)
        health = transport.health()
        self.assertTrue(health['ok'])

        target = self.workspace / 'from-one.txt'
        task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-first-write',
            'action': 'filesystem.write',
            'path': str(target),
            'content_utf8': 'hello from ONE',
        }
        self.fabric.queue_task('win-test-01', task)
        receipts = transport.run_once()
        self.assertEqual(len(receipts), 1)
        self.assertTrue(receipts[0]['ok'])
        self.assertEqual(target.read_text(encoding='utf-8'), 'hello from ONE')

        stored = self.fabric.get_receipt('task-first-write')
        self.assertIsNotNone(stored)
        self.assertTrue(stored['ok'])

        node_map = self.fabric.node_registry.node_map()
        self.assertEqual(node_map['node_count'], 1)
        self.assertEqual(node_map['nodes'][0]['status'], 'online')
        self.assertIn('filesystem.write', node_map['realm_capabilities'])

    def test_legacy_receipts_externalize_without_loss(self):
        hot = self.fabric.load()
        hot['receipts'] = {
            'legacy-a': {
                'schema': 'agentos.node-receipt/v0.1',
                'node_id': 'legacy-node',
                'task_id': 'legacy-a',
                'ok': True,
                'received_at': '2026-10-01T00:00:00Z',
            },
            'legacy-b': {
                'schema': 'agentos.node-receipt/v0.1',
                'node_id': 'legacy-node',
                'task_id': 'legacy-b',
                'ok': False,
                'received_at': '2026-10-01T00:00:01Z',
            },
        }
        self.fabric.save(hot)

        result = self.fabric.externalize_receipts()
        self.assertTrue(result['ok'])
        self.assertEqual(result['migrated_receipt_count'], 2)
        self.assertEqual(result['hot_receipt_count'], 0)
        self.assertEqual(self.fabric.load()['receipts'], {})
        self.assertTrue(Path(result['backup_path']).exists())
        self.assertTrue(self.fabric.get_receipt('legacy-a')['ok'])
        self.assertFalse(self.fabric.get_receipt('legacy-b')['ok'])

    def test_new_receipt_is_archived_not_added_to_hot_fabric(self):
        invite = self.fabric.create_invite()
        enrolled = self.fabric.enroll(
            invite_id=invite['invite_id'],
            code=invite['code'],
            manifest={
                'schema': 'agentos.node-manifest/v0.1',
                'realm_id': 'realm-test',
                'node_id': 'archive-node',
                'role': 'client',
                'hostname': 'archive-node',
                'platform': 'Darwin',
                'capabilities': [],
                'tool_presence': {},
                'surface_inventory': {'surfaces': []},
            },
        )
        stored = self.fabric.record_receipt(
            {
                'schema': 'agentos.node-receipt/v0.1',
                'realm_id': 'realm-test',
                'node_id': 'archive-node',
                'task_id': 'archive-task',
                'action': 'bounded.test',
                'ok': True,
            },
            enrolled['node_token'],
        )
        self.assertTrue(stored['ok'])
        self.assertNotIn('archive-task', self.fabric.load()['receipts'])
        archived = self.fabric.get_receipt('archive-task')
        self.assertIsNotNone(archived)
        self.assertTrue(archived['ok'])
        self.assertEqual(self.fabric.receipt_archive.count(), 1)


    def test_invite_is_one_time(self):
        invite = self.fabric.create_invite()
        policy = ThinClientPolicy(readable_roots=(self.workspace,))
        ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite['invite_id'],
            code=invite['code'],
            node_id='node-a',
            policy=policy,
            config_path=self.config_path,
        )
        with self.assertRaises(RuntimeError):
            ThinClientTransport.enroll(
                one_url=self.base_url,
                invite_id=invite['invite_id'],
                code=invite['code'],
                node_id='node-b',
                policy=policy,
                config_path=Path(self.tmp.name) / 'client-b.json',
            )


if __name__ == '__main__':
    unittest.main()
