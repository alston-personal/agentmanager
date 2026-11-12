"""Read-only Realm effective-runtime audit, no raw host secrets in projection."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile
import unittest

from scripts import inspect_realm_effective_runtime_redacted as audit


class RealmEffectiveRuntimeAuditTests(unittest.TestCase):
    @patch.object(audit, "source_provenance", return_value="a" * 40)
    @patch.object(audit, "current_release_commit", return_value="b" * 40)
    @patch.object(audit, "source_state")
    @patch.object(audit, "get_service_state")
    def test_immutable_release_without_oidc_carrier_fails_closed(self, service, source, *_):
        service.return_value = {
            "available": True, "active": True, "pid_present": True,
            "working_directory_class": "immutable_realm_release",
            "process_cwd_class": "immutable_realm_release", "execstart_realm_module": True,
        }
        source.side_effect = [
            {"readable": True, "repair_carrier_oidc_present": True, "realm_server_sha256": "a" * 64},
            {"readable": True, "repair_carrier_oidc_present": False, "realm_server_sha256": "b" * 64},
        ]
        result = audit.inspect()
        self.assertEqual(result["classification"], "REALM_LOADED_OIDC_CARRIER_ABSENT")
        self.assertFalse(result["loaded_oidc_carrier_visible_on_disk"])
        self.assertFalse(result["checkout_release_identical"])
        self.assertFalse(result["in_memory_module_proven"])
        self.assertFalse(result["production_mutations"])

    @patch.object(audit, "source_provenance", return_value=None)
    @patch.object(audit, "current_release_commit", return_value=None)
    @patch.object(audit, "source_state")
    @patch.object(audit, "get_service_state")
    def test_unknown_service_source_does_not_claim_success(self, service, source, *_):
        service.return_value = {"available": True, "active": True,
                                "working_directory_class": "other"}
        source.return_value = {"readable": True, "repair_carrier_oidc_present": True,
                               "realm_server_sha256": "c" * 64}
        result = audit.inspect()
        self.assertEqual(result["classification"], "REALM_EFFECTIVE_UNIT_UNKNOWN")

    @patch.object(audit.subprocess, "run")
    def test_raw_systemd_output_not_returned(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout="MainPID=0\nActiveState=inactive\nWorkingDirectory=/secret/path\nExecStart=python3 secret-token\n",
            stderr="secret failure",
        )
        obj = audit.get_service_state()
        self.assertFalse(obj["active"])
        self.assertNotIn("secret", json.dumps(obj))
        self.assertNotIn("/secret/path", json.dumps(obj))

    def test_source_projection_is_only_digest_and_allowlist_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "agent_core").mkdir()
            (root / "agent_core/realm_server.py").write_text(
                "secret credential\n_GITHUB_MAIN_RUNTIME_REPAIR_WORKFLOW_REF\n")
            result = audit.source_state(root)
        self.assertTrue(result["readable"])
        self.assertTrue(result["repair_carrier_oidc_present"])
        self.assertEqual(len(result["realm_server_sha256"]), 64)
        self.assertNotIn("secret", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
