"""Focused #623 Antigravity probe tests: all offline, no credentials or network."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from scripts import probe_antigravity_cli_one as probe


class ProbeTests(unittest.TestCase):
    def test_model_response_exactness(self):
        self.assertTrue(probe.model_match('{"response":"AGENTOS_GEMINI_READY"}'))
        self.assertFalse(probe.model_match('{"response":"prefix AGENTOS_GEMINI_READY"}'))
        self.assertFalse(probe.model_match('{"message":"AGENTOS_GEMINI_READY"}'))

    def test_error_classification(self):
        self.assertEqual(probe.classify_error("UNSUPPORTED_CLIENT"), "AUTH_UNSUPPORTED")
        self.assertEqual(probe.classify_error("quota exceeded"), "RATE_LIMITED")
        self.assertEqual(probe.classify_error("sign in"), "AUTH_REQUIRED")

    def test_missing_binary_fails_closed(self):
        with patch.object(probe, "BINARY", Path("/unavailable/agy")):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = probe.main()
        self.assertEqual(rc, 1)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["classification"], "BINARY_MISSING")
        self.assertFalse(payload["successful"])
        self.assertFalse(payload["credential_exposed"])

    def test_fixed_binary_and_model_call(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "agy"
            target.write_bytes(bytes((127, 69, 76, 70)) + b"test")
            target.chmod(0o700)
            calls = []

            def runner(args, *, timeout):
                calls.append((args, timeout))
                if args[-1] == "--version":
                    return CompletedProcess(args, 0, "agy 1.3.4\n", "")
                return CompletedProcess(args, 0, '{"response":"AGENTOS_GEMINI_READY"}', "")

            with patch.object(probe, "BINARY", target), patch.object(probe, "safe_run", side_effect=runner):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    rc = probe.main()
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            self.assertTrue(payload["successful"])
            self.assertEqual(payload["classification"], "ANTIGRAVITY_INFERENCE_PASS")
            self.assertEqual(payload["version"], "agy 1.3.4")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1][0][1], "-p")
            self.assertNotIn("response", payload)


if __name__ == "__main__":
    unittest.main()
