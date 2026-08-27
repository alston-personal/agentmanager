import tempfile
import unittest
from pathlib import Path

from agent_core.node_registry import NodeRegistry
from agent_core.one_uplift import BenchmarkMetrics, compare_before_after


class TestNodeRegistryV01(unittest.TestCase):
    def _manifest(self, node_id='core-test-01'):
        return {
            'schema': 'agentos.node-manifest/v0.1',
            'realm_id': 'realm-test',
            'node_id': node_id,
            'role': 'core',
            'hostname': 'core-host',
            'platform': 'Linux',
            'platform_release': 'test',
            'capabilities': ['shell.exec', 'filesystem.read'],
            'tool_presence': {'git': '/usr/bin/git'},
        }

    def test_node_map_and_benchmark_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = NodeRegistry(Path(tmp) / 'nodes.json')
            registry.register_manifest(self._manifest())
            registry.record_heartbeat({
                'schema': 'agentos.node-heartbeat/v0.1',
                'realm_id': 'realm-test',
                'node_id': 'core-test-01',
                'role': 'core',
                'status': 'online',
                'uptime_seconds': 10,
            })
            before = BenchmarkMetrics(0.5, 2, 3, 0.2, 0, 0, 0)
            after = BenchmarkMetrics(0.9, 1, 1, 0.8, 1, 1, 1)
            report = compare_before_after(before, after)
            registry.record_benchmark('core-test-01', report)

            node_map = registry.node_map()
            self.assertEqual(node_map['realm_id'], 'realm-test')
            self.assertEqual(node_map['node_count'], 1)
            self.assertEqual(node_map['online_node_count'], 1)
            self.assertIn('shell.exec', node_map['realm_capabilities'])
            self.assertIn('git', node_map['realm_tool_presence'])
            self.assertTrue(node_map['nodes'][0]['benchmark']['one_uplift_observed'])
            self.assertEqual(node_map['nodes'][0]['reported_status'], 'online')

    def test_stale_online_node_is_effectively_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = NodeRegistry(Path(tmp) / 'nodes.json')
            registry.register_manifest(self._manifest('stale-node'))
            registry.record_heartbeat({
                'schema': 'agentos.node-heartbeat/v0.1',
                'realm_id': 'realm-test',
                'node_id': 'stale-node',
                'role': 'core',
                'status': 'online',
                'observed_at': '2020-01-01T00:00:00Z',
                'uptime_seconds': 10,
            })
            node_map = registry.node_map()
            node = node_map['nodes'][0]
            self.assertEqual(node['reported_status'], 'online')
            self.assertEqual(node['status'], 'offline')
            self.assertEqual(node['status_reason'], 'heartbeat_stale')
            self.assertEqual(node_map['online_node_count'], 0)
            self.assertNotIn('shell.exec', node_map['realm_capabilities'])


if __name__ == '__main__':
    unittest.main()
