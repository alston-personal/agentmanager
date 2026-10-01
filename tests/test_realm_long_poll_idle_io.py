from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_core.node_registry import NodeRegistry
from agent_core.realm_fabric import RealmFabricStore


class RealmLongPollIdleIoTests(unittest.TestCase):
    def _store(self, root: Path) -> tuple[RealmFabricStore, str]:
        registry = NodeRegistry(root / 'nodes.json')
        store = RealmFabricStore(root / 'fabric.json', node_registry=registry)
        store.initialize_realm('realm-test')
        manifest = {
            'schema': 'agentos.node-manifest/v0.1',
            'realm_id': '',
            'node_id': 'node-1',
            'role': 'client',
            'hostname': 'node-1',
            'platform': 'Windows',
            'platform_release': 'test',
            'python_version': '3.13',
            'observed_at': '2026-10-01T00:00:00Z',
            'capabilities': [],
            'tool_presence': {},
            'surface_inventory': {'surfaces': []},
            'workspace_roots': {'readable': [], 'writable': []},
        }
        invite = store.create_invite()
        enrolled = store.enroll(invite_id=invite['invite_id'], code=invite['code'], manifest=manifest)
        return store, enrolled['node_token']

    def test_empty_pull_does_not_rewrite_fabric(self):
        with tempfile.TemporaryDirectory() as td:
            store, token = self._store(Path(td))
            before = store.path.read_bytes()
            before_mtime = store.path.stat().st_mtime_ns
            with patch.object(store, 'save', wraps=store.save) as save:
                self.assertEqual(store.pull_tasks('node-1', token), [])
                save.assert_not_called()
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(store.path.stat().st_mtime_ns, before_mtime)

    def test_nonempty_pull_consumes_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            store, token = self._store(Path(td))
            store.queue_task('node-1', {
                'schema': 'agentos.node-task/v0.1',
                'task_id': 't1',
                'action': 'desktop.session.inspect',
            })
            with patch.object(store, 'save', wraps=store.save) as save:
                tasks = store.pull_tasks('node-1', token)
                self.assertEqual([t['task_id'] for t in tasks], ['t1'])
                self.assertEqual(save.call_count, 1)
            self.assertEqual(store.load()['tasks']['node-1'], [])


if __name__ == '__main__':
    unittest.main()
