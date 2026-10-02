import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_core.one_uplift import BenchmarkMetrics, compare_before_after
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy
from agentos_node.thin_client_transport import ClientConfig, ThinClientTransport


class TestThinClient(unittest.TestCase):
    def test_manifest_and_governed_filesystem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = NodeIdentity(realm_id='realm-test', node_id='client-test-01')
            policy = ThinClientPolicy(readable_roots=(root,), writable_roots=(root,))
            client = ThinClient(identity, policy)

            manifest = client.capability_manifest()
            self.assertEqual(manifest['schema'], 'agentos.node-manifest/v0.1')
            self.assertEqual(manifest['role'], 'client')
            self.assertIn('filesystem.read', manifest['capabilities'])
            self.assertIn('filesystem.write', manifest['capabilities'])

            path = root / 'hello.txt'
            write = client.execute({
                'schema': 'agentos.node-task/v0.1',
                'task_id': 't-write',
                'action': 'filesystem.write',
                'path': str(path),
                'content_utf8': 'hello ONE',
            })
            self.assertTrue(write['ok'])

            read = client.execute({
                'schema': 'agentos.node-task/v0.1',
                'task_id': 't-read',
                'action': 'filesystem.read',
                'path': str(path),
            })
            self.assertTrue(read['ok'])
            self.assertEqual(read['content_utf8'], 'hello ONE')

    def test_shell_requires_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = ThinClient(
                NodeIdentity('realm-test', 'client-test-02'),
                ThinClientPolicy(readable_roots=(root,)),
            )
            receipt = client.execute({
                'schema': 'agentos.node-task/v0.1',
                'task_id': 't-shell',
                'action': 'shell.exec',
                'executable': 'python3',
                'argv': ['-c', 'print(1)'],
                'cwd': str(root),
            })
            self.assertFalse(receipt['ok'])
            self.assertIn('not allowlisted', receipt['error'])


    def test_successful_heartbeat_writes_local_liveness_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = ThinClientPolicy(readable_roots=(root,), writable_roots=(root,))
            client = ThinClient(NodeIdentity('realm-test', 'client-heartbeat-01'), policy)
            config = ClientConfig(
                one_url='http://127.0.0.1:8780',
                realm_id='realm-test',
                node_id='client-heartbeat-01',
                node_token='test-token',
            )
            transport = ThinClientTransport(client, config)
            marker = root / 'heartbeat.json'

            with mock.patch.dict(os.environ, {'AGENTOS_CLIENT_HOME': str(root)}, clear=False):
                with mock.patch.object(ThinClientTransport, '_request', return_value={'ok': True}):
                    result = transport.heartbeat()

            self.assertTrue(result['ok'])
            self.assertTrue(marker.exists())
            payload = json.loads(marker.read_text(encoding='utf-8'))
            self.assertEqual(payload['schema'], 'agentos.local-heartbeat/v0.1')
            self.assertEqual(payload['node_id'], 'client-heartbeat-01')
            self.assertEqual(payload['realm_id'], 'realm-test')
            self.assertIsNotNone(payload['recorded_at_epoch'])

    def test_uplift_dimensions(self):
        before = BenchmarkMetrics(
            task_success=0.5,
            repeated_errors=3,
            user_clarifications=4,
            continuity_recovery=0.2,
            realm_capability_usage=0,
            inherited_cognition_usage=0,
            evidence_returned=0,
        )
        after = BenchmarkMetrics(
            task_success=0.9,
            repeated_errors=1,
            user_clarifications=2,
            continuity_recovery=0.9,
            realm_capability_usage=2,
            inherited_cognition_usage=1,
            evidence_returned=1,
        )
        report = compare_before_after(before, after)
        self.assertTrue(report['one_uplift_observed'])
        self.assertEqual(report['regressed_dimensions'], 0)
        self.assertGreater(report['uplift']['task_success'], 0)


if __name__ == '__main__':
    unittest.main()
