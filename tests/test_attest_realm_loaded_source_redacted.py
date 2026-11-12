"""Bounded Realm 8780 process audit contract tests: no secrets or raw config."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts.attest_realm_loaded_source_redacted import parse_environ, sha256, source_attestation

class RealmSourceRedactionTests(unittest.TestCase):
    def test_only_pythonpath_is_parsed(self):
        env = (b"HOME=/home/private\0AGENTOS_CONTROLLER_TOKEN=very-secret\0"
               b"PYTHONPATH=/home/ubuntu/agentmanager:/srv/release-a\0")
        result = parse_environ(env)
        self.assertEqual([str(v) for v in result], [
            "/home/ubuntu/agentmanager/agent_core/realm_server.py",
            "/srv/release-a/agent_core/realm_server.py",
        ])
        self.assertNotIn("very-secret", repr(result))

    def test_file_digest_does_not_disclose_content(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "realm.py"
            path.write_text("secret signing key", encoding="utf-8")
            digest = sha256(path)
            self.assertIsNotNone(digest)
            self.assertEqual(len(digest), 64)
            self.assertNotIn("secret", digest)

    @patch("scripts.attest_realm_loaded_source_redacted.probe_health", return_value=True)
    @patch("scripts.attest_realm_loaded_source_redacted.active_unit_state", return_value=("active", None))
    def test_even_healthy_site_cannot_claim_runtime_release(self, unit, health):
        result = source_attestation()
        self.assertTrue(result["unit_active"])
        self.assertTrue(result["health_schema_valid"])
        self.assertFalse(result["release_accepted"])
        self.assertFalse(result["loaded_module_in_memory_verified"])
        self.assertFalse(result["conclusive_8780_origin_verified"])
        self.assertFalse(result["credential_exposed"])
        self.assertNotIn("pid", result)
        self.assertNotIn("environment", result)
        self.assertNotIn("source_path", result)

if __name__ == "__main__":
    unittest.main()
