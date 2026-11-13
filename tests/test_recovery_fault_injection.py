from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "scripts/windows/recovery_one_probe.py"


class RecoveryIsolationFaultInjectionTests(unittest.TestCase):
    def invoke_with_broken_normal_runtime(self, *, one_available):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            # Deliberately poison the normal runtime import path and package.
            poison = root / "agentos_node"
            poison.mkdir()
            (poison / "__init__.py").write_text(
                "raise RuntimeError('NORMAL_RUNTIME_BROKEN')\n", encoding="utf-8")
            config = root / "client.json"
            status = root / "recovery" / "status.json"
            config.write_text(json.dumps({
                "one_url": "https://agentos.milkcat.org",
                "realm_id": "realm-alston",
                "node_id": "broken-client",
                "node_token": "s" * 32,
            }), encoding="utf-8")
            # The process runs in isolated Python mode and uses only stdlib.
            # Intercept the network in this CHILD process, never call a real ONE.
            body = r"""
import runpy
import sys
import urllib.request
sys.path.insert(0, POISON)
class FakeResponse:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self, size): return b'{"schema":"agentos.node-bootstrap/v0.1","node_id":"broken-client","realm_id":"realm-alston"}'
class FakeOpener:
    def open(self, req, timeout):
        if not IS_ONLINE:
            raise OSError("ONE_UNAVAILABLE")
        if req.get_header("Authorization") != "Bearer " + "s"*32:
            raise AssertionError("invalid token")
        return FakeResponse()
urllib.request.build_opener = lambda *args: FakeOpener()
sys.argv = [SCRIPT, "--config", CONFIG, "--status", STATUS]
runpy.run_path(SCRIPT, run_name="__main__")
"""
            code = (
                "POISON=" + repr(str(root)) + "\n"
                + "SCRIPT=" + repr(str(PROBE)) + "\n"
                + "CONFIG=" + repr(str(config)) + "\n"
                + "STATUS=" + repr(str(status)) + "\n"
                + "IS_ONLINE=" + repr(one_available) + "\n"
                + body
            )
            result = subprocess.run(
                [sys.executable, "-I", "-c", code], capture_output=True,
                text=True, cwd=str(root), timeout=15,
                env={**os.environ, "PYTHONPATH": str(root)},
            )
            self.assertTrue(status.exists(), result.stderr)
            return result, json.loads(status.read_text(encoding="utf-8"))

    def test_recovery_roundtrip_when_normal_runtime_is_poisoned(self):
        proc, status = self.invoke_with_broken_normal_runtime(one_available=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(status["one_transport_roundtrip"])
        self.assertFalse(status["recovery_update_authorized"])
        self.assertNotIn("NORMAL_RUNTIME_BROKEN", proc.stderr)
        self.assertNotIn("s"*32, proc.stdout)

    def test_recovery_failure_is_explicit_when_one_unavailable(self):
        proc, status = self.invoke_with_broken_normal_runtime(one_available=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse(status["one_transport_roundtrip"])
        self.assertFalse(status["recovery_update_authorized"])
        self.assertEqual(status["error_class"], "OSError")
        self.assertNotIn("s"*32, proc.stdout)


if __name__ == "__main__":
    unittest.main()
