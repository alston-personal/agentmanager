"""Bounded Realm 8780 process audit contract tests: no secrets or raw config."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts.attest_realm_loaded_source_redacted import parse_environ, sha256, source_attestation, is_realm_8780_command, has_main_runtime_repair_policy, unit_source_candidate

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

    @patch.dict("os.environ", {"AGENTOS_REALM_ATTEST_EXPECTED_SHA256": "invalid"})
    def test_trusted_baseline_rejects_invalid_source_digest(self):
        with self.assertRaisesRegex(ValueError, "exact lowercase SHA256"):
            source_attestation()

    def test_canonical_attestation_uses_actual_ubuntu_service_identity(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/oracle-attest-realm-fabric-process.yml").read_text(encoding="utf-8")
        assert "runs-on: ubuntu-latest" in workflow
        assert 'test "${DEPLOY_USER:-}" = ubuntu' in workflow
        assert "AGENTOS_REALM_ATTEST_ROOT=/home/ubuntu/agentmanager" in workflow
        assert "AGENTOS_REALM_ATTEST_EXPECTED_SHA256=$EXPECTED_SHA" in workflow
        assert "< scripts/attest_realm_loaded_source_redacted.py" in workflow
        assert "systemctl --user restart" not in workflow

    def test_bounded_proc_listener_match_never_leaks_argv(self):
        fixed = b"python3\0-m\0agent_core.realm_cli\0serve\0--port\08780\0"
        self.assertTrue(is_realm_8780_command(fixed))
        self.assertFalse(is_realm_8780_command(b"python3\0-m\0some.other.module\0serve\08780\0"))
        self.assertFalse(is_realm_8780_command(b"python3\0-m\0agent_core.realm_cli\0serve\09999\0"))

    def test_oidc_policy_probe_only_exposes_boolean(self):
        with TemporaryDirectory() as root:
            candidate = Path(root) / "realm_server.py"
            candidate.write_text(
                "_GITHUB_MAIN_RUNTIME_REPAIR_WORKFLOW_REF\n"
                "main-action-runtime-migration-20261007.yml\n"
                "_validate_main_runtime_repair_intent\n"
                "private-secret-is-never-returned",
                encoding="utf-8",
            )
            self.assertIs(has_main_runtime_repair_policy(candidate), True)
            self.assertIs(has_main_runtime_repair_policy(Path(root) / "absent.py"), False)

    @patch("scripts.attest_realm_loaded_source_redacted.subprocess.check_output",
           return_value="/home/ubuntu/.local/share/agentos/realm-fabric/current\\n")
    def test_realm_unit_immutable_workdir_is_a_separate_source_candidate(self, check):
        path, category = unit_source_candidate()
        self.assertEqual(category, "realm_immutable_or_current")
        self.assertEqual(path.name, "realm_server.py")
        self.assertNotIn("secret", repr(category))

    @patch("scripts.attest_realm_loaded_source_redacted.subprocess.check_output",
           return_value="/home/ubuntu/agentmanager")
    def test_legacy_mutable_unit_workdir_is_not_mislabeled_immutable(self, check):
        _, category = unit_source_candidate()
        self.assertEqual(category, "mutable_source_checkout")

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
        self.assertIn("unit_mainpid_is_listener", result)
        self.assertIn("checkout_main_runtime_oidc_policy_present", result)
        self.assertIn("process_candidate_main_runtime_oidc_policy_present", result)
        self.assertIn("unit_source_candidate_matches_expected", result)
        self.assertIn("unit_source_candidate_has_main_runtime_oidc_policy", result)
        self.assertNotIn("pid", result)
        self.assertNotIn("environment", result)
        self.assertNotIn("source_path", result)

if __name__ == "__main__":
    unittest.main()
