"""Known unsupported Gemini OAuth clients should not be re-probed each job."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/"capabilities/wardrobe_visual_review/gemini_backend.py"
spec=importlib.util.spec_from_file_location("mio_gemini_breaker",SOURCE)
backend=importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class TerminalOauthRegression(unittest.TestCase):
    def test_persistent_breaker_survives_independent_calls(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"AGENT_DATA_ROOT":root}):
                self.assertFalse(backend._is_terminal_oauth_blocked("runtime-a"))
                backend._record_terminal_oauth("runtime-a")
                self.assertTrue(backend._is_terminal_oauth_blocked("runtime-a"))
                self.assertFalse(backend._is_terminal_oauth_blocked("runtime-b"))
                receipt=json.loads((Path(root)/"provider_health/gemini-cli/oauth-client-terminal.json").read_text())
                self.assertEqual(receipt["classification"],"OAUTH_CLIENT_UNSUPPORTED")
                self.assertFalse(receipt["routable"])
                self.assertEqual(receipt["retryPolicy"],"require_runtime_or_auth_method_change")

    def test_known_terminal_blocks_without_invoking_reviewer(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.dict(os.environ, {"AGENT_DATA_ROOT":root}):
                backend._record_terminal_oauth("runtime-a")
                with patch.object(backend,"_find_gemini",return_value="/fake/gemini"),patch.object(backend,"_provider_breaker_identity",return_value="runtime-a"),patch.object(backend.subprocess,"run",side_effect=AssertionError("CLI MUST NOT RUN")):
                    result=backend.review_with_gemini(job={},candidate_path=Path(root)/"missing.webp",workspace_root=Path(root)/"review")
                self.assertEqual(result["classification"],"OAUTH_CLIENT_UNSUPPORTED")
                self.assertFalse(result["backendReady"])

    def test_detection_classifies_nested_ineligible_tier(self):
        signal="Error: IneligibleTierError: This client is no longer supported. Migrate to Antigravity."
        self.assertEqual(backend._classify_failure(signal),"OAUTH_CLIENT_UNSUPPORTED")

if __name__=="__main__": unittest.main()
