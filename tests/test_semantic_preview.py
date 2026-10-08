import json
import subprocess
import unittest
from unittest import mock

from agentos_node import semantic_preview as semantic_preview_module


class FakeProcess:
    def __init__(self, *, stdout="", stderr="", returncode=0, timeout=False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._timeout = timeout
        self.killed = False

    def communicate(self, input=None, timeout=None):
        if self._timeout and not self.killed:
            raise subprocess.TimeoutExpired(
                cmd="semantic-worker",
                timeout=timeout,
                stderr="STAGE=capture_bmp\n",
            )
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


class TestSemanticPreviewIsolation(unittest.TestCase):
    def test_subprocess_timeout_is_bounded_and_reports_stage(self):
        fake = FakeProcess(timeout=True)
        with mock.patch.object(semantic_preview_module, "_require_windows"), \
             mock.patch.object(semantic_preview_module.subprocess, "Popen", return_value=fake):
            with self.assertRaisesRegex(TimeoutError, "stage=capture_bmp"):
                semantic_preview_module.semantic_preview({"timeout_seconds": 2})
        self.assertTrue(fake.killed)

    def test_subprocess_result_is_returned_with_isolation_metadata(self):
        result = {
            "schema": "agentos.desktop-semantic-preview/v0.1",
            "read_only": True,
            "mode": "foreground-window-only",
            "state_hash": "abc",
            "foreground": {},
            "preview": {},
        }
        fake = FakeProcess(
            stdout=json.dumps({"ok": True, "result": result}),
            stderr="STAGE=session_info\nSTAGE=foreground_window\nSTAGE=capture_bmp\n",
            returncode=0,
        )
        with mock.patch.object(semantic_preview_module, "_require_windows"), \
             mock.patch.object(semantic_preview_module.subprocess, "Popen", return_value=fake):
            returned = semantic_preview_module.semantic_preview({"timeout_seconds": 2})
        self.assertTrue(returned["worker"]["isolated"])
        self.assertEqual(returned["worker"]["transport"], "subprocess")
        self.assertEqual(returned["worker"]["last_stage"], "capture_bmp")
        self.assertTrue(returned["read_only"])


if __name__ == "__main__":
    unittest.main()
