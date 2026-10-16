"""Tests for the side-effect-free bounty GitHub credential probe."""
import importlib.util
from pathlib import Path
import sys
import unittest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "bounty_github_delivery_probe.py"
SPEC = importlib.util.spec_from_file_location("bounty_github_delivery_probe", FILE)
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


class DeliveryProbeTests(unittest.TestCase):
    def test_missing_credentials_does_not_attempt_api(self):
        def fail(_request, **_kwargs):
            self.fail("must not call GitHub without token")
        receipt = mod.probe_repository("owner/repo", "", fail)
        self.assertEqual(receipt.outcome, "AUTH_REQUIRED")

    def test_forbidden_upstream_is_auth_required(self):
        receipt = mod.classify_http("github.pr.comment", "other/repo", 403)
        self.assertEqual(receipt.outcome, "AUTH_REQUIRED")
        self.assertEqual(receipt.http_status, 403)

    def test_not_found_is_not_automatically_permission_failure(self):
        receipt = mod.classify_http("github.repo.read", "other/repo", 404)
        self.assertEqual(receipt.outcome, "NOT_FOUND")

    def test_accepted_status_is_ready(self):
        self.assertEqual(mod.classify_http("github.repo.read", "a/b", 200).outcome, "READY")

    def test_transient_outage_bounded_by_supervisor(self):
        self.assertEqual(mod.classify_http("github.repo.read", "a/b", 503).outcome, "RETRYABLE")

    def test_receipt_does_not_store_token(self):
        receipt = mod.probe_repository("a/b", "")
        self.assertNotIn("secret", receipt.to_json())
        self.assertEqual(receipt.repository, "a/b")


    def test_atomic_receipt(self):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "receipts" / "github.json"
            receipt = mod.classify_http("github.repo.read", "a/b", 403)
            mod.persist_receipt(str(path), receipt)
            self.assertEqual(json.loads(path.read_text())["outcome"], "AUTH_REQUIRED")

if __name__ == "__main__":
    unittest.main()
