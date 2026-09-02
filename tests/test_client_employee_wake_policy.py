from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from agentos_node.client_cli import _load_policy, main
from agentos_node.thin_client import NodeIdentity, ThinClient


WAKE_CAPABILITY = 'agent.employee.wake.deliver'


class ClientEmployeeWakePolicyTests(unittest.TestCase):
    def _write_policy(self, root: Path, *, wake_root=None, allowed=None, writable=None) -> Path:
        path = root / 'policy.json'
        payload = {
            'schema': 'agentos.client-policy/v0.1',
            'allowed_executables': list(allowed or []),
            'readable_roots': [],
            'writable_roots': list(writable or []),
            'employee_wake_root': wake_root,
            'max_timeout_seconds': 120,
        }
        path.write_text(json.dumps(payload) + '\n', encoding='utf-8')
        return path

    def test_null_wake_root_does_not_advertise_capability(self):
        with tempfile.TemporaryDirectory() as td:
            policy = _load_policy(self._write_policy(Path(td), wake_root=None))
            self.assertIsNone(policy.employee_wake_root)
            manifest = ThinClient(NodeIdentity('realm-test', 'node-test'), policy).capability_manifest()
            self.assertNotIn(WAKE_CAPABILITY, manifest['capabilities'])

    def test_absolute_wake_root_loads_and_advertises_only_typed_wake(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            wake_root = (root / 'wake').resolve()
            policy = _load_policy(self._write_policy(root, wake_root=str(wake_root)))
            self.assertEqual(policy.employee_wake_root, wake_root)
            self.assertEqual(policy.writable_roots, ())
            self.assertEqual(policy.allowed_executables, set())
            manifest = ThinClient(NodeIdentity('realm-test', 'node-test'), policy).capability_manifest()
            self.assertIn(WAKE_CAPABILITY, manifest['capabilities'])
            self.assertNotIn('filesystem.write', manifest['capabilities'])
            self.assertNotIn('shell.exec', manifest['capabilities'])

    def test_relative_wake_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write_policy(Path(td), wake_root='relative/wake')
            with self.assertRaisesRegex(ValueError, 'employee_wake_root_must_be_absolute'):
                _load_policy(path)

    def test_non_string_wake_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._write_policy(Path(td), wake_root=['not', 'a', 'path'])
            with self.assertRaisesRegex(ValueError, 'employee_wake_root_must_be_string_or_null'):
                _load_policy(path)

    def test_policy_init_defaults_wake_capability_off(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy_path = root / 'policy.json'
            with redirect_stdout(StringIO()):
                rc = main(['--policy', str(policy_path), 'policy-init', '--root', str(root / 'workspace')])
            self.assertEqual(rc, 0)
            payload = json.loads(policy_path.read_text(encoding='utf-8'))
            self.assertIsNone(payload['employee_wake_root'])

    def test_policy_init_persists_explicit_absolute_wake_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy_path = root / 'policy.json'
            wake_root = (root / 'employee-wake').resolve()
            with redirect_stdout(StringIO()):
                rc = main([
                    '--policy', str(policy_path),
                    'policy-init',
                    '--root', str(root / 'workspace'),
                    '--employee-wake-root', str(wake_root),
                ])
            self.assertEqual(rc, 0)
            payload = json.loads(policy_path.read_text(encoding='utf-8'))
            self.assertEqual(payload['employee_wake_root'], str(wake_root))
            self.assertNotIn(str(wake_root), payload['writable_roots'])

    def test_policy_init_rejects_relative_wake_root_without_writing_policy(self):
        with tempfile.TemporaryDirectory() as td:
            policy_path = Path(td) / 'policy.json'
            stderr = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(stderr):
                rc = main([
                    '--policy', str(policy_path),
                    'policy-init',
                    '--employee-wake-root', 'relative/wake',
                ])
            self.assertEqual(rc, 2)
            self.assertIn('employee_wake_root_must_be_absolute', stderr.getvalue())
            self.assertFalse(policy_path.exists())


if __name__ == '__main__':
    unittest.main()
