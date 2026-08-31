import tempfile
import unittest
from pathlib import Path

from agentos_node.executor_registry import DESKTOP_CAPABILITIES, ExecutorRegistry
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


class TestExecutorRegistry(unittest.TestCase):
    def test_non_windows_keeps_desktop_unavailable(self):
        registry = ExecutorRegistry(platform_name='Linux')
        desktop = registry.desktop()
        self.assertEqual(desktop.status, 'unavailable')
        self.assertEqual(desktop.reason, 'unsupported_platform')
        self.assertEqual(desktop.capabilities, ())

    def test_windows_service_session_does_not_advertise_desktop(self):
        registry = ExecutorRegistry(
            platform_name='Windows',
            desktop_probe=lambda: {
                'process_session_id': 0,
                'active_console_session_id': 2,
                'interactive': False,
            },
        )
        desktop = registry.desktop()
        self.assertEqual(desktop.status, 'unavailable')
        self.assertEqual(desktop.reason, 'not_interactive_session')
        self.assertEqual(desktop.capabilities, ())

    def test_windows_interactive_session_advertises_desktop(self):
        registry = ExecutorRegistry(
            platform_name='Windows',
            desktop_probe=lambda: {
                'process_session_id': 2,
                'active_console_session_id': 2,
                'interactive': True,
            },
        )
        desktop = registry.desktop()
        self.assertEqual(desktop.status, 'available')
        self.assertEqual(set(desktop.capabilities), set(DESKTOP_CAPABILITIES))

    def test_manifest_separates_node_from_desktop_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = ExecutorRegistry(
                platform_name='Windows',
                desktop_probe=lambda: {
                    'process_session_id': 0,
                    'active_console_session_id': 2,
                    'interactive': False,
                },
            )
            client = ThinClient(
                NodeIdentity('realm-test', 'node-service-test'),
                ThinClientPolicy(readable_roots=(root,), writable_roots=(root,)),
                executor_registry=registry,
            )
            manifest = client.capability_manifest()
            self.assertIn('filesystem.read', manifest['capabilities'])
            self.assertNotIn('desktop.screenshot', manifest['capabilities'])
            executors = {item['executor_id']: item for item in manifest['executors']}
            self.assertEqual(executors['local']['status'], 'available')
            self.assertEqual(executors['desktop']['status'], 'unavailable')

    def test_desktop_dispatch_fails_closed_when_executor_unavailable(self):
        registry = ExecutorRegistry(
            platform_name='Windows',
            desktop_probe=lambda: {
                'process_session_id': 0,
                'active_console_session_id': 2,
                'interactive': False,
            },
        )
        client = ThinClient(
            NodeIdentity('realm-test', 'node-service-test'),
            ThinClientPolicy(),
            executor_registry=registry,
        )
        receipt = client.execute({
            'schema': 'agentos.node-task/v0.1',
            'task_id': 'desktop-fail-closed',
            'action': 'desktop.open_url',
            'url': 'https://example.com',
        })
        self.assertFalse(receipt['ok'])
        self.assertIn('desktop executor unavailable', receipt['error'])


if __name__ == '__main__':
    unittest.main()
