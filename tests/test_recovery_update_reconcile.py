from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

WINDOWS = Path(__file__).resolve().parents[1] / "scripts/windows"
sys.path.insert(0, str(WINDOWS))
import recovery_slot_runner as slots
import recovery_update_reconcile as audit

SCHEMA = "agentos.dual-channel-update-state/v1"


class RecoveryCrossStoreReconciliationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "recovery"
        source = Path(tmp.name) / "initial.py"
        source.write_text("print('lkg')\n")
        slots.bootstrap(self.root, source)
        self.operation = "recovery-upgrade-001"

    def gate(self, phase="IDLE", lane=None, operation=None):
        return {
            "schema": SCHEMA, "phase": phase,
            "active_lane": lane, "operation_id": operation,
            "generation": 4,
        }

    def check(self, **kwargs):
        return audit.reconcile(root=self.root, participant_id="windows-node",
                               gate=self.gate(**kwargs))

    def staged(self, *, activated=False, corrupt=False):
        state = slots.load_state(self.root)
        path = self.root / "slot-B" / "recovery_one_probe.py"
        path.parent.mkdir()
        path.write_text("print('candidate')\n")
        stage = {
            "schema": audit.STAGE_SCHEMA,
            "operation_id": self.operation, "slot": "B",
            "active": "A", "node_id": "windows-node",
            "realm_id": "realm-alston",
            "candidate_sha256": slots.digest(path),
            "activation_authorized": False,
            "one_receipt_attested": False,
        }
        slots.atomic_json(self.root / "staged-candidate.json", stage)
        (self.root / "stage-reservation.lock").write_text(self.operation + "\n")
        if activated:
            slots.atomic_json(self.root / "slots.json", {
                **state, "active": "B", "pending": "B",
                "digests": {**state["digests"], "B": slots.digest(path)},
            })
        if corrupt:
            path.write_text("corrupted")

    def test_idle_and_clean_only_eligible_for_review_not_authorized(self):
        result = self.check()
        self.assertEqual(result["classification"], "READY")
        self.assertTrue(result["eligible_for_authoritative_review"])
        self.assertFalse(result["new_update_permitted"])
        self.assertFalse(result["activation_authorized"])

    def test_begin_committed_but_stage_missing_freezes(self):
        result = self.check(phase="STAGED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")
        self.assertFalse(result["new_update_permitted"])

    def test_stage_complete_but_activation_not_yet_attempted(self):
        self.staged()
        result = self.check(phase="STAGED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "AWAITING_AUTHORITATIVE_ACTIVATION")
        self.assertFalse(result["activation_authorized"])

    def test_activation_gate_precedes_slot_commit_freezes(self):
        self.staged()
        result = self.check(phase="ACTIVATED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")

    def test_slot_switched_but_one_receipt_missing(self):
        self.staged(activated=True)
        result = self.check(phase="ACTIVATED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "AWAITING_ONE_RECEIPT")
        self.assertFalse(result["one_receipt_attested"])
        self.assertEqual(result["lkg_slot"], "A")

    def test_local_slot_accepted_but_one_gate_not_finished_freezes(self):
        self.staged(activated=True)
        state = slots.load_state(self.root)
        slots.atomic_json(self.root / "slots.json",
                          {**state, "last_known_good": "B", "pending": None})
        result = self.check(phase="ACTIVATED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")

    def test_one_gate_cleared_first_and_stage_reservation_remains_freezes(self):
        self.staged()
        result = self.check()
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")

    def test_corrupted_lkg_requires_human(self):
        (self.root / "slot-A" / "recovery_one_probe.py").write_text("tampered")
        self.assertEqual(self.check()["classification"], "HUMAN_REQUIRED_LKG_CORRUPT")

    def test_corrupt_pending_candidate_does_not_become_healthy(self):
        self.staged(activated=True, corrupt=True)
        result = self.check(phase="ACTIVATED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")
        self.assertFalse(result["active_integrity_verified"])

    def test_rollback_pending_requires_separate_authority(self):
        self.staged(activated=True)
        result = self.check(phase="ROLLBACK_REQUIRED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "AWAITING_AUTHORIZED_ROLLBACK")
        self.assertFalse(result["rollback_authorized"])

    def test_corrupt_pending_B_still_waits_for_authorized_rollback(self):
        self.staged(activated=True, corrupt=True)
        result = self.check(phase="ROLLBACK_REQUIRED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "AWAITING_AUTHORIZED_ROLLBACK")
        self.assertFalse(result["active_integrity_verified"])
        self.assertTrue(result["lkg_integrity_verified"])
        self.assertFalse(result["rollback_authorized"])
        self.assertFalse(result["new_update_permitted"])
        self.assertFalse(result["one_receipt_attested"])
        self.assertEqual(slots.load_state(self.root)["pending"], "B")

    def test_corrupt_pending_B_with_wrong_operation_stays_frozen(self):
        self.staged(activated=True, corrupt=True)
        result = self.check(phase="ROLLBACK_REQUIRED", lane="recovery",
                            operation="unrelated-operation")
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")
        self.assertFalse(result["rollback_authorized"])

    def test_corrupt_pending_B_and_lkg_requires_human(self):
        self.staged(activated=True, corrupt=True)
        (self.root / "slot-A" / "recovery_one_probe.py").write_text("lkg-damaged")
        result = self.check(phase="ROLLBACK_REQUIRED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"], "HUMAN_REQUIRED_LKG_CORRUPT")
        self.assertFalse(result["rollback_authorized"])

    def test_local_revert_committed_but_one_gate_still_locked(self):
        self.staged(activated=True, corrupt=True)
        state = slots.load_state(self.root)
        slots.atomic_json(self.root / "slots.json",
                          {**state, "active": "A", "pending": None})
        result = self.check(phase="ROLLBACK_REQUIRED", lane="recovery",
                            operation=self.operation)
        self.assertEqual(result["classification"],
                         "GOVERNED_POST_ROLLBACK_RECONCILIATION")
        self.assertFalse(result["rollback_authorized"])
        self.assertFalse(result["new_update_permitted"])
        self.assertFalse(result["one_receipt_attested"])
        self.assertTrue((self.root / "stage-reservation.lock").exists())

    def test_local_revert_with_operation_mismatch_stays_blocked(self):
        self.staged(activated=True)
        state = slots.load_state(self.root)
        slots.atomic_json(self.root / "slots.json",
                          {**state, "active": "A", "pending": None})
        result = self.check(phase="ROLLBACK_REQUIRED", lane="recovery",
                            operation="unrelated")
        self.assertEqual(result["classification"],
                         "GOVERNED_RECONCILIATION_REQUIRED")
        self.assertFalse(result["rollback_authorized"])

    def test_stale_operation_mismatch_blocks(self):
        self.staged()
        result = self.check(phase="STAGED", lane="recovery",
                            operation="different-operation")
        self.assertEqual(result["classification"], "GOVERNED_RECONCILIATION_REQUIRED")

    def test_other_lane_and_untrusted_gate_fail(self):
        with self.assertRaises(ValueError):
            self.check(phase="STAGED", lane="normal", operation=self.operation)
        with self.assertRaises(ValueError):
            audit.reconcile(root=self.root,
                            gate={"schema":"fake"}, participant_id="windows-node")


if __name__ == "__main__":
    unittest.main()
