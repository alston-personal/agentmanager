import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.executor_bridge import FileExecutorBridge, FileExecutorHost, describe_executor_bridge
from agentos_node.executor_registry import DESKTOP_CAPABILITIES, ExecutorRegistry
from agentos_node.thin_client import NodeIdentity, ThinClient, ThinClientPolicy


class TestExecutorBridge(unittest.TestCase):
    def test_descriptor_reports_fresh_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = FileExecutorHost('desktop', tmp, capabilities=['desktop.open_url'])
            host.publish_descriptor(ready=True)
            descriptor = describe_executor_bridge('desktop', tmp)
            self.assertIsNotNone(descriptor)
            self.assertTrue(descriptor['ready'])
            self.assertEqual(descriptor['status'], 'available')
            self.assertIn('desktop.open_url', descriptor['capabilities'])

    def test_request_receipt_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge = FileExecutorBridge('desktop', tmp)
            host = FileExecutorHost('desktop', tmp, capabilities=['desktop.open_url'])
            host.publish_descriptor(ready=True)
            task = {
                'schema': 'agentos.node-task/v0.1',
                'task_id': 'bridge-roundtrip',
                'action': 'desktop.open_url',
                'url': 'https://example.com',
            }
            request = bridge.request(task)
            self.assertEqual(host.serve_once(lambda item: {'echo_action': item['action']}), 1)
            receipt = bridge.receipt(request['request_id'])
            self.assertTrue(receipt['ok'])
            self.assertEqual(receipt['result']['echo_action'], 'desktop.open_url')

    def test_node_service_routes_to_bridged_desktop_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = FileExecutorHost('desktop', root, capabilities=DESKTOP_CAPABILITIES)
            host.publish_descriptor(ready=True)
            registry = ExecutorRegistry(
                platform_name='Windows',
                desktop_probe=lambda: {
                    'process_session_id': 0,
                    'active_console_session_id': 2,
                    'interactive': False,
                },
                desktop_bridge_probe=lambda: describe_executor_bridge('desktop', root),
            )
            client = ThinClient(
                NodeIdentity('realm-test', 'node-service-test'),
                ThinClientPolicy(max_timeout_seconds=2),
                executor_registry=registry,
            )
            manifest = client.capability_manifest()
            executors = {item['executor_id']: item for item in manifest['executors']}
            self.assertEqual(executors['desktop']['kind'], 'interactive-desktop-bridge')
            self.assertIn('desktop.open_url', manifest['capabilities'])

            stop = threading.Event()

            def worker():
                while not stop.is_set():
                    host.serve_once(lambda task: {'bridged': True, 'url': task.get('url')})
                    time.sleep(0.02)

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            try:
                with patch.dict(os.environ, {'AGENTOS_DESKTOP_EXECUTOR_BRIDGE': str(root)}):
                    receipt = client.execute({
                        'schema': 'agentos.node-task/v0.1',
                        'task_id': 'bridged-open-url',
                        'action': 'desktop.open_url',
                        'url': 'https://example.com',
                    })
                self.assertTrue(receipt['ok'], receipt)
                self.assertTrue(receipt['bridged'])
                self.assertEqual(receipt['url'], 'https://example.com')
            finally:
                stop.set()
                thread.join(timeout=1)


if __name__ == '__main__':
    unittest.main()
