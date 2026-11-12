from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/windows"
sys.path.insert(0, str(SCRIPTS))
import recovery_slot_runner as slot
import recovery_upgrade_promotion as promote


class RecoveryPromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "recovery"
        old = Path(self.temp.name) / "old.py"
        old.write_text("print('old')\n")
        slot.bootstrap(self.root, old)
        self.op = "recovery-op-001"
        candidate = self.root / "slot-B" / "recovery_one_probe.py"
        candidate.parent.mkdir()
        candidate.write_text("print('new')\n")
        self.sha = slot.digest(candidate)
        self.record = {
            "schema": promote.STAGED_SCHEMA,
            "operation_id": self.op, "slot": "B",
            "node_id": "node-1", "realm_id": "realm-alston",
            "candidate_sha256": self.sha, "active": "A",
            "activation_authorized": False, "one_receipt_attested": False,
        }
        slot.atomic_json(self.root / "staged-candidate.json", self.record)
        (self.root / "stage-reservation.lock").write_text(self.op + "\n")

    def activate(self, auth=lambda _c: True, normal=lambda _c: True,
                 gate=lambda _c, _s: True):
        return promote.activate_pending(
            root=self.root, operation_id=self.op,
            authorize_activation=auth, normal_channel_live=normal,
            durable_update_gate=gate,
        )

    def accept(self, candidate=lambda _c: True, normal=lambda _c: True,
               receipt=lambda _c: True, gate=lambda _c, _s: True):
        return promote.accept_pending(
            root=self.root, operation_id=self.op,
            verify_candidate_one=candidate, verify_normal_live=normal,
            verify_one_receipt=receipt, durable_update_gate=gate,
        )

    def test_activate_preserves_previous_lkg(self):
        state = self.activate()
        self.assertEqual(state["active"], "B")
        self.assertEqual(state["pending"], "B")
        self.assertEqual(state["last_known_good"], "A")
        self.assertEqual(state["digests"]["B"], self.sha)
        self.assertTrue((self.root / "stage-reservation.lock").exists())

    def test_accept_requires_live_one_and_receipt_then_promotes(self):
        self.activate()
        with self.assertRaises(PermissionError):
            self.accept(receipt=lambda _c: False)
        self.assertEqual(slot.load_state(self.root)["last_known_good"], "A")
        result = self.accept()
        self.assertEqual(result["active"], "B")
        self.assertEqual(result["last_known_good"], "B")
        self.assertIsNone(result["pending"])
        self.assertTrue((self.root / "stage-reservation.lock").exists())

    def test_activation_refused_when_authority_or_normal_fails(self):
        for denied in ("auth", "normal", "gate"):
            with self.subTest(denied=denied):
                try:
                    self.activate(
                        auth=lambda _c: denied != "auth",
                        normal=lambda _c: denied != "normal",
                        gate=lambda _c, _s: denied != "gate",
                    )
                except PermissionError:
                    pass
                else:
                    self.fail("expected denied promotion")
                state = slot.load_state(self.root)
                self.assertEqual(state["active"], "A")
                self.assertIsNone(state["pending"])

    def test_candidate_tamper_blocks_activation(self):
        (self.root / "slot-B" / "recovery_one_probe.py").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "candidate_changed_since_staging"):
            self.activate()
        self.assertEqual(slot.load_state(self.root)["active"], "A")

    def test_orphan_reservation_or_stage_mismatch_blocks(self):
        (self.root / "stage-reservation.lock").unlink()
        with self.assertRaises(ValueError):
            self.activate()
        (self.root / "stage-reservation.lock").write_text("wrong-op")
        with self.assertRaises(ValueError):
            self.activate()
        self.assertEqual(slot.load_state(self.root)["active"], "A")

    def test_verified_lkg_revert_after_candidate_failure(self):
        self.activate()
        result = promote.revert_pending(
            root=self.root, operation_id=self.op,
            verify_lkg_one=lambda _c: True,
            durable_update_gate=lambda _c, _s: True,
        )
        self.assertEqual(result["active"], "A")
        self.assertEqual(result["last_known_good"], "A")
        self.assertIsNone(result["pending"])

    def test_lkg_corruption_blocks_revert(self):
        self.activate()
        (self.root / "slot-A" / "recovery_one_probe.py").write_text("tamper")
        with self.assertRaisesRegex(ValueError, "human_required"):
            promote.revert_pending(
                root=self.root, operation_id=self.op,
                verify_lkg_one=lambda _c: True,
                durable_update_gate=lambda _c, _s: True,
            )
        self.assertEqual(slot.load_state(self.root)["active"], "B")

    def test_unauthorized_json_flags_never_grant_acceptance(self):
        self.activate()
        self.record["one_receipt_attested"] = True
        slot.atomic_json(self.root / "staged-candidate.json", self.record)
        with self.assertRaises(ValueError):
            self.accept()
        self.assertEqual(slot.load_state(self.root)["last_known_good"], "A")


if __name__ == "__main__":
    unittest.main()
