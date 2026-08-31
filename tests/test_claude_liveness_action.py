import subprocess
import unittest
from unittest.mock import patch

from agentos_node.action_relay import (
    ACTIONS,
    CLAUDE_LIVENESS_MARKER,
    _claude_liveness_diagnose,
)


class ClaudeLivenessActionTests(unittest.TestCase):
    def test_action_is_allowlisted_but_not_generic_shell(self):
        self.assertIn("agentos.claude.liveness_diagnose", ACTIONS)
        with self.assertRaises(ValueError):
            _claude_liveness_diagnose({"probe": "shell.exec"})
        with self.assertRaises(ValueError):
            _claude_liveness_diagnose({"probe": "auth_status", "argv": ["id"]})

    @patch("agentos_node.antigravity_relay_worker.discover_executor")
    @patch("agentos_node.action_relay.subprocess.run")
    def test_headless_probe_returns_sanitized_marker_evidence(self, run, discover):
        discover.return_value = ("claude", ["/tmp/anthropic.claude-code-2.1.251-linux-arm64/resources/native-binary/claude"])
        run.return_value = subprocess.CompletedProcess([], 0, stdout=CLAUDE_LIVENESS_MARKER + "\n", stderr="")
        result = _claude_liveness_diagnose({"probe": "headless_print"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["probe_ok"])
        self.assertEqual(result["executor_version"], "2.1.251")
        self.assertFalse(result["raw_output_persisted"])
        self.assertNotIn("stdout", result["result"])
        self.assertNotIn("stderr", result["result"])
        self.assertNotIn("argv", result["result"])
        self.assertTrue(result["result"]["marker_present"])
        invoked = run.call_args.args[0]
        self.assertIn("--print", invoked)
        self.assertNotIn("--restricted", invoked)
        self.assertNotIn("--bare", invoked)

    @patch("agentos_node.antigravity_relay_worker.discover_executor")
    @patch("agentos_node.action_relay.subprocess.run")
    def test_restricted_probe_is_fixed_and_reports_unsupported(self, run, discover):
        discover.return_value = ("claude", ["/tmp/claude"])
        run.return_value = subprocess.CompletedProcess([], 2, stdout="", stderr="unknown option --restricted")
        result = _claude_liveness_diagnose({"probe": "restricted_headless_print"})
        self.assertTrue(result["ok"])
        self.assertFalse(result["probe_ok"])
        self.assertFalse(result["result"]["supported"])
        self.assertIn("--restricted", run.call_args.args[0])
        self.assertNotIn("--bare", run.call_args.args[0])

    @patch("agentos_node.antigravity_relay_worker.discover_executor")
    @patch("agentos_node.action_relay.subprocess.run")
    def test_auth_status_classification_does_not_persist_output(self, run, discover):
        discover.return_value = ("claude", ["/tmp/claude"])
        run.return_value = subprocess.CompletedProcess([], 0, stdout="Authenticated as hidden@example.invalid", stderr="")
        result = _claude_liveness_diagnose({"probe": "auth_status"})
        self.assertEqual(result["result"]["auth_state"], "authenticated")
        self.assertNotIn("hidden@example.invalid", repr(result))

    @patch("agentos_node.antigravity_relay_worker.discover_executor")
    @patch("agentos_node.action_relay.subprocess.run")
    def test_timeout_is_terminal_sanitized_evidence(self, run, discover):
        discover.return_value = ("claude", ["/tmp/claude"])
        run.side_effect = subprocess.TimeoutExpired(["/tmp/claude"], 30, output=b"partial", stderr=b"")
        result = _claude_liveness_diagnose({"probe": "headless_print"})
        self.assertTrue(result["result"]["timed_out"])
        self.assertEqual(result["result"]["returncode"], 124)
        self.assertFalse(result["probe_ok"])
        self.assertNotIn("partial", repr(result))


if __name__ == "__main__":
    unittest.main()
