import json
from pathlib import Path
from unittest.mock import patch
import subprocess
import unittest

from scripts.inspect_realm_oidc_process_readonly import inspect

SHA = "a" * 40
CARRIER = "main-action-runtime-migration-20261007.yml"
SOURCE = (
    "_GITHUB_MAIN_RUNTIME_REPAIR_WORKFLOW_REF = '" + CARRIER + "'\n"
    "main_runtime_repair_carrier = True\n"
).encode()

class RealmOidcProcessAttestationTests(unittest.TestCase):
    @patch("scripts.inspect_realm_oidc_process_readonly.Path.read_bytes")
    @patch("scripts.inspect_realm_oidc_process_readonly.Path.resolve")
    @patch("scripts.inspect_realm_oidc_process_readonly.Path.exists")
    @patch("scripts.inspect_realm_oidc_process_readonly._fixed")
    def test_matching_disk_is_not_loaded_runtime_proof(self, run, exists, resolve, read):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, b"1234\n", b""),
            subprocess.CompletedProcess([], 0, SOURCE, b""),
        ]
        exists.return_value = True
        resolve.return_value = Path("/home/ubuntu/agentmanager")
        read.return_value = SOURCE
        result = inspect(SHA)
        self.assertEqual(result["classification"], "REALM_DISK_MATCHES_BUT_LOADED_MODULE_UNVERIFIED")
        self.assertFalse(result["authoritative_loaded_module_proved"])
        self.assertEqual(result["result"], "BLOCKED")
        self.assertNotIn("credentials", json.dumps(result))

    @patch("scripts.inspect_realm_oidc_process_readonly.Path.read_bytes")
    @patch("scripts.inspect_realm_oidc_process_readonly.Path.resolve")
    @patch("scripts.inspect_realm_oidc_process_readonly.Path.exists")
    @patch("scripts.inspect_realm_oidc_process_readonly._fixed")
    def test_different_process_cwd_is_reported_without_path_leak(self, run, exists, resolve, read):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, b"1234\n", b""),
            subprocess.CompletedProcess([], 0, SOURCE, b""),
        ]
        exists.return_value = True
        resolve.return_value = Path("/secret/other-runtime")
        read.return_value = SOURCE
        result = inspect(SHA)
        self.assertEqual(result["classification"], "REALM_PROCESS_SOURCE_ROOT_MISMATCH")
        self.assertNotIn("/secret/other-runtime", json.dumps(result))
        self.assertFalse(result["authoritative_loaded_module_proved"])

    def test_invalid_sha_and_arbitrary_inputs_are_rejected(self):
        for value in ("main", "A" * 40, "a" * 39, "../../file"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                inspect(value)

    @patch("scripts.inspect_realm_oidc_process_readonly.Path.read_bytes")
    @patch("scripts.inspect_realm_oidc_process_readonly._fixed")
    def test_missing_service_cannot_claim_runtime_ready(self, run, read):
        run.side_effect = [
            subprocess.CompletedProcess([], 1, b"", b"secret-content"),
            subprocess.CompletedProcess([], 0, SOURCE, b""),
        ]
        read.return_value = SOURCE
        result = inspect(SHA)
        self.assertEqual(result["classification"], "REALM_PROCESS_UNOBSERVED")
        self.assertNotIn("secret-content", json.dumps(result))

if __name__ == "__main__":
    unittest.main()
