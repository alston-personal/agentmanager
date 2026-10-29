#!/usr/bin/env python3
"""Pure contract tests for LeopardCat production backend release preflight."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch
import subprocess

MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "leopardcat_backend_release_preflight.py"
spec = importlib.util.spec_from_file_location("tarot_preflight", MODULE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

VALID_SHA = "a" * 40


class PreflightContract(unittest.TestCase):
    def test_rejects_non_sha_before_commands(self):
        with patch.object(preflight, "command") as command:
            with self.assertRaisesRegex(ValueError, "target_sha_not_exact"):
                preflight.inspect("main")
            command.assert_not_called()

    def test_preflight_checks_user_scoped_tarot_service(self):
        with patch.object(preflight, "command", return_value="/unexpected"):
            with self.assertRaisesRegex(RuntimeError, "unexpected_service_working_directory"):
                preflight.inspect(VALID_SHA)
            preflight.command.assert_called_once_with(
                "systemctl", "--user", "show", "leopardcat-tarot.service",
                "-p", "WorkingDirectory", "--value"
            )

    def test_rejects_wrong_systemd_workdir(self):
        with patch.object(preflight, "command", return_value="/tmp/untrusted"):
            with self.assertRaisesRegex(RuntimeError, "unexpected_service_working_directory"):
                preflight.inspect(VALID_SHA)

    def test_rejects_unapproved_dirty_file(self):
        values = iter([
            str(preflight.APP), "active",
            "https://github.com/alston-personal/leopardcat-tarot.git",
            "b" * 40, "main", " M website/fortune_server.py"
        ])
        with patch.object(preflight, "command", side_effect=lambda *args: next(values)):
            with self.assertRaisesRegex(RuntimeError, "unexpected_runtime_dirty_paths"):
                preflight.inspect(VALID_SHA)

    def test_rejects_target_not_on_main(self):
        values = iter([
            str(preflight.APP), "active",
            "https://github.com/alston-personal/leopardcat-tarot.git",
            "b" * 40, "main", "", "", "c" * 40
        ])
        ok = subprocess.CompletedProcess([], 0)
        bad = subprocess.CompletedProcess([], 1)
        with patch.object(preflight, "command", side_effect=lambda *args: next(values)):
            with patch.object(preflight.subprocess, "run", side_effect=[ok, bad]):
                with self.assertRaisesRegex(RuntimeError, "target_not_on_main_release_lane"):
                    preflight.inspect(VALID_SHA)


if __name__ == "__main__":
    unittest.main()
