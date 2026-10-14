"""Unit tests for the bounded Antigravity Executor Job provider."""
import json
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from agent_core.executor_job_contract import canonical_executor_job_request, validate_executor_job
from agentos_node.antigravity_cli_probe_provider import run_antigravity_probe
from agentos_node.executor_job_adapter import ExecutorJobProviderRegistry
from agentos_node.antigravity_cli_probe_provider import register_antigravity_probe_provider


class AntigravityJobTests(unittest.TestCase):
    def setUp(self):
        self.request = canonical_executor_job_request("antigravity.cli.probe")

    def test_job_is_read_only(self):
        self.assertTrue(validate_executor_job(self.request).read_only)

    def test_registration(self):
        registry = ExecutorJobProviderRegistry()
        self.assertTrue(register_antigravity_probe_provider(registry=registry))
        self.assertEqual(registry.get("antigravity.cli.probe").executor_class, "antigravity-cli")

    def test_missing_script_fails_closed(self):
        with tempfile.TemporaryDirectory() as dirname:
            result = run_antigravity_probe(self.request, runtime_root=Path(dirname))
        self.assertEqual(result["classification"], "PROBE_NOT_DEPLOYED")
        self.assertFalse(result["successful"])

    def test_valid_sanitized_receipt(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            script = root / "scripts/probe_antigravity_cli_one.py"
            script.parent.mkdir()
            script.write_text("# placeholder")
            response = {"schema": "agentos.antigravity-cli-probe/v1",
                        "classification": "ANTIGRAVITY_INFERENCE_PASS",
                        "successful": True, "expected_marker_matched": True,
                        "version": "agy 1.3.4", "sha256": "a" * 64,
                        "secret": "SHOULD_NOT_ESCAPE"}
            with patch("agentos_node.antigravity_cli_probe_provider.subprocess.run",
                       return_value=CompletedProcess([], 0, json.dumps(response), "")):
                result = run_antigravity_probe(self.request, runtime_root=root)
        self.assertTrue(result["successful"])
        self.assertEqual(result["agy_probe_sha256"], "a" * 64)
        self.assertNotIn("secret", result)

    def test_successful_false_even_if_verdict_text_passes(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            script = root / "scripts/probe_antigravity_cli_one.py"
            script.parent.mkdir()
            script.write_text("# placeholder")
            response = {"schema": "agentos.antigravity-cli-probe/v1",
                        "classification": "ANTIGRAVITY_INFERENCE_PASS",
                        "successful": True, "expected_marker_matched": True}
            with patch("agentos_node.antigravity_cli_probe_provider.subprocess.run",
                       return_value=CompletedProcess([], 1, json.dumps(response), "")):
                result = run_antigravity_probe(self.request, runtime_root=root)
        self.assertFalse(result["successful"])


if __name__ == "__main__":
    unittest.main()
