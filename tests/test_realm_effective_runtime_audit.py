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

    @patch.object(audit.pwd, "getpwuid")
    @patch.object(Path, "resolve")
    @patch.object(Path, "stat")
    @patch.object(Path, "read_bytes")
    @patch.object(Path, "iterdir")
    def test_bounded_candidate_owner_projection_never_exposes_process_data(
        self, iterdir, read_bytes, stat, resolve, getpwuid
    ):
        iterdir.return_value = [Path("/proc/777")]
        read_bytes.return_value = (
            b"/usr/bin/python3\0-m\0agent_core.realm_cli\0serve\0"
            b"secret-session-token\0"
        )
        stat.return_value = SimpleNamespace(st_uid=1001)
        resolve.return_value = Path("/untrusted/runtime/location")
        getpwuid.return_value = SimpleNamespace(pw_name="agentos-node")
        result = audit.bounded_realm_process_candidates()
        self.assertEqual(result["candidate_owner_class"], "agentos-node")
        self.assertEqual(result["candidate_count_band"], "one")
        self.assertFalse(result["candidate_owns_8780_proved"])
        for secret in ("777", "secret-session-token", "/untrusted/runtime/location"):
            self.assertNotIn(secret, json.dumps(result))

    @patch.object(audit, "bounded_realm_process_candidates")
    @patch.object(audit, "source_provenance", return_value=None)
    @patch.object(audit, "current_release_commit", return_value=None)
    @patch.object(audit, "source_state", return_value={"readable": False, "repair_carrier_oidc_present": False})
    @patch.object(audit, "get_service_state", return_value={"available": False, "active": False, "pid_present": False})
    def test_different_service_owner_is_classified_without_claiming_release(
        self, _service, _source, _release, _provenance, candidates
    ):
        candidates.return_value = {
            "candidate_process_detected": True,
            "candidate_count_band": "one",
            "candidate_owner_class": "agentos-node",
            "candidate_workdir_class": "unknown",
            "candidate_owns_8780_proved": False,
        }
        result = audit.inspect()
        self.assertTrue(result["runner_user_service_mismatch_suspected"])
        self.assertEqual(result["classification"], "REALM_SERVICE_UNAVAILABLE")
        self.assertFalse(result["in_memory_module_proven"])

    @patch.object(audit, "_APPROVED_SOURCE_ROOTS", (Path("/tmp/allowed-root"),))
    @patch.object(audit, "source_state")
    @patch.object(Path, "resolve")
    def test_effective_workdir_source_approved_without_revealing_path_or_content(self, resolve, source):
        resolve.return_value = Path("/tmp/allowed-root/release-1")
        source.return_value = {
            "readable": True,
            "repair_carrier_oidc_present": False,
            "realm_server_sha256": "f" * 64,
        }
        result = audit.observed_workdir_source(Path("/tmp/private"))
        self.assertTrue(result["approved_root"])
        self.assertTrue(result["source_readable"])
        self.assertFalse(result["oidc_repair_carrier_present"])
        self.assertEqual(result["source_sha256"], "f" * 64)
        self.assertNotIn("/tmp/private", json.dumps(result))

    @patch.object(audit, "_APPROVED_SOURCE_ROOTS", (Path("/tmp/allowed-root"),))
    @patch.object(audit, "source_state")
    @patch.object(Path, "resolve")
    def test_effective_workdir_outside_approved_root_is_rejected(self, resolve, source):
        resolve.return_value = Path("/etc/private/runtime")
        result = audit.observed_workdir_source(Path("/tmp/injected"))
        self.assertFalse(result["approved_root"])
        self.assertFalse(result["source_readable"])
        source.assert_not_called()

    @patch.object(audit, "bounded_realm_process_candidates")
    @patch.object(audit, "source_provenance", return_value=None)
    @patch.object(audit, "current_release_commit", return_value=None)
    @patch.object(audit, "source_state")
    @patch.object(audit, "get_service_state")
    def test_effective_workdir_old_oidc_beats_checkout_symbol(self, service, source, *_):
        service.return_value = {
            "available": True, "active": True, "pid_present": True,
            "working_directory_class": "other", "process_cwd_class": "other",
            "configured_workdir_source": {"approved_root": True, "source_readable": True,
                "oidc_repair_carrier_present": False, "source_sha256": "a" * 64},
            "process_cwd_source": {"approved_root": True, "source_readable": True,
                "oidc_repair_carrier_present": False, "source_sha256": "a" * 64},
        }
        source.side_effect = [
            {"readable": True, "repair_carrier_oidc_present": True, "realm_server_sha256": "b" * 64},
            {"readable": False, "repair_carrier_oidc_present": False},
        ]
        result = audit.inspect()
        self.assertEqual(result["classification"], "REALM_EFFECTIVE_SOURCE_OIDC_ABSENT")
        self.assertFalse(result["effective_workdir_oidc_carrier_visible_on_disk"])
        self.assertFalse(result["in_memory_module_proven"])

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
