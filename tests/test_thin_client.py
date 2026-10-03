import tempfile
import unittest
from pathlib import Path

from agent_core.one_uplift import BenchmarkMetrics, compare_before_after
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


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

    def test_manifest_and_actions_expose_fast_executor_inventory(self):
        from unittest import mock

        inventory = {
            'schema': 'agentos.executor-inventory/v0.2',
            'executors': [{
                'executor_id': 'claude-code',
                'state': 'DISCOVERED',
                'health_deferred': True,
                'routable': False,
            }],
        }
        client = ThinClient(
            NodeIdentity('realm-test', 'client-executor-01'),
            ThinClientPolicy(),
        )
        with mock.patch(
            'agentos_node.executor_reconcile.discover_executor_inventory',
            return_value=inventory,
        ) as discover:
            manifest = client.capability_manifest()
            receipt = client.execute({
                'schema': 'agentos.node-task/v0.1',
                'task_id': 'executor-discover',
                'action': 'agent.executor.discover',
            })
        self.assertIn('agent.executor.discover', manifest['capabilities'])
        self.assertIn('agent.executor.reconcile', manifest['capabilities'])
        self.assertEqual(manifest['executor_inventory'], inventory)
        self.assertTrue(receipt['ok'])
        self.assertEqual(receipt['executor_inventory'], inventory)
        for call in discover.call_args_list:
            self.assertEqual(call.kwargs.get('probe_health'), False)

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

    def test_manifest_advertises_ready_session_bridge_capabilities(self):
        with tempfile.TemporaryDirectory() as tmp:
            import json
            import os
            root = Path(tmp)
            bridge = root / 'bridge'
            bridge.mkdir()
            (bridge / 'bridge.json').write_text(json.dumps({
                'schema': 'agentos.session-bridge/v0.1',
                'provider': 'gemini',
                'ready': True,
                'operations': ['discover', 'snapshot', 'harvest', 'handoff']
            }), encoding='utf-8')
            old = os.environ.get('AGENTOS_GEMINI_BRIDGE')
            os.environ['AGENTOS_GEMINI_BRIDGE'] = str(bridge)
            try:
                client = ThinClient(
                    NodeIdentity('realm-test', 'client-session-01'),
                    ThinClientPolicy(readable_roots=(root,)),
                )
                caps = client.capability_manifest()['capabilities']
                self.assertIn('agent.session.discover', caps)
                self.assertIn('agent.session.inspect', caps)
                self.assertIn('agent.context.harvest', caps)
                self.assertIn('agent.session.handoff', caps)
                self.assertIn('agent.session.receipt', caps)
            finally:
                if old is None:
                    os.environ.pop('AGENTOS_GEMINI_BRIDGE', None)
                else:
                    os.environ['AGENTOS_GEMINI_BRIDGE'] = old

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


    def test_linux_ssh_inspect_and_recover_are_bounded(self):
        import os
        import platform
        from unittest import mock

        client = ThinClient(
            NodeIdentity('realm-test', 'oracle-exec'),
            ThinClientPolicy(),
        )

        def fake_run(argv, **kwargs):
            class Result:
                def __init__(self, returncode=0, stdout="", stderr=""):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr
            if argv[-3:] == ['systemctl', 'is-active', 'ssh']:
                return Result(0, 'active\n', '')
            if argv[-2:] == ['ss', '-lnt']:
                return Result(0, 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n', '')
            if argv[-3:] == ['systemctl', 'restart', 'ssh']:
                return Result(0, '', '')
            raise AssertionError(argv)

        with mock.patch.object(platform, 'system', return_value='Linux'), \
             mock.patch.object(os, 'geteuid', return_value=1000), \
             mock.patch('agentos_node.thin_client.subprocess.run', side_effect=fake_run):
            inspect = client.execute({
                'schema': 'agentos.node-task/v0.1',
                'task_id': 'ssh-inspect',
                'action': 'node.ssh.inspect',
            })
            self.assertTrue(inspect['ok'])
            self.assertTrue(inspect['ssh_service_active'])
            self.assertTrue(inspect['port22_listening'])

            recover = client.execute({
                'schema': 'agentos.node-task/v0.1',
                'task_id': 'ssh-recover',
                'action': 'node.ssh.recover',
            })
            self.assertTrue(recover['ok'])
            self.assertTrue(recover['recovered'])


if __name__ == '__main__':
    unittest.main()
