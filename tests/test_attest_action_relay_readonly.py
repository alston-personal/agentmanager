"""Pure, no-Oracle tests for redacted Action Relay source readback."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.attest_action_relay_readonly import SCHEMA, assess

SHA = "a" * 40


class ActionRelayReadOnlyAttestationTest(unittest.TestCase):
    def evaluate(self, **changes):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = {
                "active": "active", "workdir": str(root),
                "unit_environment": "SECRET=never_print_this AGENTOS_ACTION_RUNTIME_SOURCE_REF=main "
                                    + "AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT=" + SHA,
                "runtime_head": SHA, "runtime_status": "",
                "marker": {"schema": "agentos.action-relay-capabilities/v1",
                           "source_ref": "main", "source_commit": SHA},
                "pending": False, "root": root,
            }
            inputs.update(changes)
            result = assess(**inputs)
            self.assertNotIn("SECRET", json.dumps(result))
            self.assertNotIn(str(root), json.dumps(result))
            self.assertEqual(result["schema"], SCHEMA)
            self.assertFalse(result["live_process_import_proven"])
            self.assertFalse(result["production_rollback_proven"])
            self.assertFalse(result["rescue_channel_proven"])
            return result

    def test_matching_disk_unit_and_marker_is_observed_not_live_import_proof(self):
        self.assertTrue(self.evaluate()["verified_disk_and_unit_generation"])

    def test_mismatch_between_unit_and_worktree_fails_closed(self):
        result = self.evaluate(runtime_head="b" * 40)
        self.assertFalse(result["verified_disk_and_unit_generation"])
        self.assertFalse(result["unit_marker_runtime_sha_match"])

    def test_marker_tampering_fails_closed(self):
        marker = {"schema": "agentos.action-relay-capabilities/v1",
                  "source_ref": "main", "source_commit": "b" * 40}
        self.assertFalse(self.evaluate(marker=marker)["verified_disk_and_unit_generation"])

    def test_dirty_or_untracked_files_fail_closed(self):
        self.assertFalse(self.evaluate(runtime_status="?? residue.py")["verified_disk_and_unit_generation"])

    def test_pending_transaction_blocks_verification(self):
        result = self.evaluate(pending=True)
        self.assertFalse(result["verified_disk_and_unit_generation"])
        self.assertTrue(result["pending_transaction"])

    def test_working_directory_mismatch_blocks_verification(self):
        self.assertFalse(self.evaluate(workdir="/dev/null")["verified_disk_and_unit_generation"])

    def test_unknown_source_ref_rejected_and_redacted(self):
        result = self.evaluate(unit_environment="AGENTOS_ACTION_RUNTIME_SOURCE_REF=secret "
                                               + "AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT=" + SHA)
        self.assertFalse(result["verified_disk_and_unit_generation"])
        self.assertEqual(result["source_ref_class"], "unknown")

    def test_invalid_marker_schema_is_rejected(self):
        marker = {"schema": "incorrect", "source_ref": "main", "source_commit": SHA}
        self.assertFalse(self.evaluate(marker=marker)["verified_disk_and_unit_generation"])

    def test_absent_and_failed_reads_not_accepted(self):
        self.assertFalse(self.evaluate(active=None, runtime_status=None)["verified_disk_and_unit_generation"])


if __name__ == "__main__":
    unittest.main()
