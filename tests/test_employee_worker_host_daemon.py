from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.employee_worker_host_daemon import _singleton_lock, build_host


class EmployeeWorkerHostDaemonTests(unittest.TestCase):
    def test_build_host_requires_explicit_wake_root_and_node_identity(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_DATA_ROOT": str(base / "data"),
                    "AGENTOS_EMPLOYEE_WAKE_ROOT": str(base / "wake"),
                    "AGENTOS_EMPLOYEE_WORKER_NODE_ID": "oracle-core",
                },
                clear=True,
            ):
                host = build_host()
        self.assertEqual(host.node_id, "oracle-core")
        self.assertTrue(host.runtime_root.is_absolute())
        self.assertTrue(host.wake_root.is_absolute())

    def test_build_host_fails_closed_without_wake_root(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_DATA_ROOT": str(Path(td) / "data"),
                    "AGENTOS_EMPLOYEE_WORKER_NODE_ID": "oracle-core",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(ValueError, "agentos_employee_wake_root_required"):
                    build_host()

    def test_singleton_lock_rejects_second_process_owner(self):
        if os.name == "nt":
            self.skipTest("hosted CI lock overlap is covered on POSIX; Windows uses msvcrt")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with _singleton_lock(root):
                with self.assertRaisesRegex(RuntimeError, "process_already_active"):
                    with _singleton_lock(root):
                        pass


if __name__ == "__main__":
    unittest.main()
