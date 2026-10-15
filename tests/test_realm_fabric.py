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


    def test_task_pull_is_leased_until_receipt(self):
        invite = self.fabric.create_invite(expires_minutes=5, label='lease-node')
        policy = ThinClientPolicy(readable_roots=(self.workspace,))
        config = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite['invite_id'],
            code=invite['code'],
            node_id='lease-node',
            policy=policy,
            config_path=self.config_path,
        )

        task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-lease',
            'action': 'desktop.session.inspect',
        }
        self.fabric.queue_task('lease-node', task)

        first = self.fabric.pull_tasks('lease-node', config.node_token)
        self.assertEqual([item['task_id'] for item in first], ['task-lease'])

        leased_store = self.fabric.load()['tasks']['lease-node']
        self.assertEqual(len(leased_store), 1)
        self.assertEqual(leased_store[0]['task_id'], 'task-lease')
        self.assertEqual(leased_store[0]['_lease_count'], 1)
        self.assertTrue(leased_store[0]['_lease_until'])

        second = self.fabric.pull_tasks('lease-node', config.node_token)
        self.assertEqual(second, [])

        receipt = {
            'schema': 'agentos.node-receipt/v0.1',
            'realm_id': 'realm-test',
            'node_id': 'lease-node',
            'task_id': 'task-lease',
            'action': 'desktop.session.inspect',
            'ok': True,
        }
        self.fabric.record_receipt(receipt, config.node_token)

        self.assertEqual(self.fabric.load()['tasks']['lease-node'], [])
        self.assertTrue(self.fabric.get_receipt('task-lease')['ok'])


    def test_concurrent_transport_mutations_preserve_receipt(self):
        import threading

        invite = self.fabric.create_invite(expires_minutes=5, label='concurrency-node')
        policy = ThinClientPolicy(readable_roots=(self.workspace,))
        config = ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite['invite_id'],
            code=invite['code'],
            node_id='concurrency-node',
            policy=policy,
            config_path=self.config_path,
        )

        task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'task-concurrent-receipt',
            'action': 'desktop.session.inspect',
        }
        self.fabric.queue_task('concurrency-node', task)
        pulled = self.fabric.pull_tasks('concurrency-node', config.node_token)
        self.assertEqual([x['task_id'] for x in pulled], ['task-concurrent-receipt'])

        receipt = {
            'schema': 'agentos.node-receipt/v0.1',
            'realm_id': 'realm-test',
            'node_id': 'concurrency-node',
            'task_id': 'task-concurrent-receipt',
            'action': 'desktop.session.inspect',
            'ok': True,
        }
        heartbeat = {
            'schema': 'agentos.node-heartbeat/v0.1',
            'realm_id': 'realm-test',
            'node_id': 'concurrency-node',
            'observed_at': '2026-10-12T00:00:00Z',
            'status': 'online',
            'capabilities': [],
        }

        errors = []
        def write_receipt():
            try:
                RealmFabricStore(self.fabric.path, node_registry=self.fabric.node_registry).record_receipt(receipt, config.node_token)
            except Exception as exc:
                errors.append(exc)

        def write_heartbeats():
            try:
                other = RealmFabricStore(self.fabric.path, node_registry=self.fabric.node_registry)
                for _ in range(25):
                    other.record_heartbeat(heartbeat, config.node_token)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write_receipt), threading.Thread(target=write_heartbeats)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        stored = self.fabric.load()
        # Stable receipt API works for hot legacy state and durable archive.
        archived = self.fabric.get_receipt('task-concurrent-receipt')
        self.assertIsNotNone(archived)
        self.assertTrue(archived['ok'])
        self.assertEqual(stored['tasks']['concurrency-node'], [])

    def test_concurrent_queue_mutations_do_not_drop_tasks(self):
        import threading

        invite = self.fabric.create_invite(expires_minutes=5, label='queue-node')
        policy = ThinClientPolicy(readable_roots=(self.workspace,))
        ThinClientTransport.enroll(
            one_url=self.base_url,
            invite_id=invite['invite_id'],
            code=invite['code'],
            node_id='queue-node',
            policy=policy,
            config_path=self.config_path,
        )

        errors = []
        def enqueue(index):
            try:
                RealmFabricStore(self.fabric.path, node_registry=self.fabric.node_registry).queue_task(
                    'queue-node',
                    {
                        'schema': 'agentos.node-task/v0.1',
                        'task_id': f'task-concurrent-{index}',
                        'action': 'desktop.session.inspect',
                    },
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=enqueue, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        queued = self.fabric.load()['tasks']['queue-node']
        self.assertEqual(len(queued), 20)
        self.assertEqual({x['task_id'] for x in queued}, {f'task-concurrent-{i}' for i in range(20)})

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
