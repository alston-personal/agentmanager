from __future__ import annotations

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agentos_node import spec_steward_worker_cli as cli


class SpecStewardWorkerCliTests(unittest.TestCase):
    def test_cli_requires_absolute_roots_and_explicit_once(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--runtime-root", "relative/runtime",
                    "--wake-root", "/tmp/wake",
                    "--worker-state-root", "/tmp/state",
                    "--node-id", "node-o3",
                    "--once",
                ]
            )
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "--runtime-root", "/tmp/runtime",
                    "--wake-root", "/tmp/wake",
                    "--worker-state-root", "/tmp/state",
                    "--node-id", "node-o3",
                ]
            )

    def test_cli_exposes_no_provider_session_shell_or_argv_switches(self):
        parser = cli.build_parser()
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        for forbidden in (
            "--provider",
            "--model",
            "--session",
            "--session-id",
            "--shell",
            "--command",
            "--argv",
            "--url",
            "--token",
            "--credential",
        ):
            self.assertNotIn(forbidden, option_strings)

    def test_cli_uses_governed_wrapper_and_outputs_sanitized_state(self):
        state = SimpleNamespace(
            status="checkpointed",
            employee_id="agentos-spec-steward",
            assignment_id="spec-steward-o3-acceptance-v1",
            lease_generation=1,
            thread_head="o3:checkpoint:g1:abc",
            error_code=None,
            executor_provider="agentos-native-spec-audit",
            executor_model="spec-audit-v1",
            process_instance_digest="must-not-print",
        )
        fake_worker = SimpleNamespace(process_one=lambda: state)
        out = io.StringIO()
        with patch.object(cli, "GovernedSpecStewardWakeWorker", return_value=fake_worker) as factory:
            with patch("sys.stdout", out):
                code = cli.main(
                    [
                        "--runtime-root", "/tmp/runtime",
                        "--wake-root", "/tmp/wake",
                        "--worker-state-root", "/tmp/state",
                        "--node-id", "node-o3",
                        "--once",
                    ]
                )
        self.assertEqual(code, 0)
        factory.assert_called_once()
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "checkpointed")
        self.assertFalse(payload["verified_marker_emitted"])
        self.assertFalse(payload["credential_exposed"])
        self.assertFalse(payload["session_identity_exposed"])
        self.assertNotIn("process_instance_digest", payload)
        self.assertNotIn("must-not-print", out.getvalue())

    def test_idle_cli_is_success_and_never_claims_verification(self):
        fake_worker = SimpleNamespace(process_one=lambda: None)
        out = io.StringIO()
        with patch.object(cli, "GovernedSpecStewardWakeWorker", return_value=fake_worker):
            with patch("sys.stdout", out):
                code = cli.main(
                    [
                        "--runtime-root", "/tmp/runtime",
                        "--wake-root", "/tmp/wake",
                        "--worker-state-root", "/tmp/state",
                        "--node-id", "node-o3",
                        "--once",
                    ]
                )
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "idle")
        self.assertFalse(payload["verified_marker_emitted"])


if __name__ == "__main__":
    unittest.main()
