from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/windows"
spec = importlib.util.spec_from_file_location(
    "recovery_upgrade_stage", SCRIPTS / "recovery_upgrade_stage.py"
)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
slot_spec = importlib.util.spec_from_file_location(
    "recovery_slot_runner", SCRIPTS / "recovery_slot_runner.py"
)
slot = importlib.util.module_from_spec(slot_spec)
slot_spec.loader.exec_module(slot)


class RecoveryStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "recovery"
        self.old = Path(self.tmp.name) / "old.py"
        self.old.write_text("print('known good')\n", encoding="utf-8")
        slot.bootstrap(self.root, self.old)
        self.new = Path(self.tmp.name) / "new.py"
        self.new.write_text("print('candidate')\n", encoding="utf-8")
        self.manifest = {
            "schema": stage.SCHEMA,
            "candidate_sha256": hashlib.sha256(self.new.read_bytes()).hexdigest(),
            "node_id": "win-node", "realm_id": "realm-alston",
            "operation_id": "recovery-upgrade-001",
        }
        self.old_state = slot.load_state(self.root)
        self._path = list(sys.path)
        sys.path.insert(0, str(SCRIPTS))
        self.addCleanup(lambda: setattr(sys, "path", self._path))

    def call(self, authority=lambda _m: True,
             normal=lambda _m: True, isolated=lambda _p, _m: True):
        return stage.stage_inactive_candidate(
            root=self.root, source=self.new, manifest=self.manifest,
            trusted_one_verifier=authority,
            live_normal_rescue_probe=normal,
            isolated_candidate_test=isolated,
        )

    def test_staging_does_not_activate_or_replace_lkg(self):
        result = self.call()
        self.assertFalse(result["activation_authorized"])
        self.assertFalse(result["one_receipt_attested"])
        self.assertEqual(result["slot"], "B")
        self.assertEqual(slot.load_state(self.root), self.old_state)
        self.assertEqual(
            (self.root / "slot-A" / "recovery_one_probe.py").read_bytes(),
            self.old.read_bytes(),
        )
        self.assertEqual((self.root / "slot-B" / "recovery_one_probe.py").read_bytes(),
                         self.new.read_bytes())
        self.assertEqual(json.loads((self.root / "staged-candidate.json").read_text()),
                         result)
        with self.assertRaises(ValueError):
            self.call()

    def test_failed_authority_normal_or_isolated_test_leaves_old_slot_intact(self):
        for gate in ("authority", "normal", "isolated"):
            with self.subTest(gate=gate):
                checks = {
                    "authority": lambda _m: gate != "authority",
                    "normal": lambda _m: gate != "normal",
                    "isolated": lambda _p, _m: gate != "isolated",
                }
                with self.assertRaises((PermissionError, RuntimeError)):
                    self.call(authority=checks["authority"],
                              normal=checks["normal"], isolated=checks["isolated"])
                self.assertFalse((self.root / "slot-B").exists())
                self.assertFalse((self.root / "stage-reservation.lock").exists())
                self.assertEqual(slot.load_state(self.root), self.old_state)

    def test_digest_tamper_and_invalid_manifest_fail_closed(self):
        self.new.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest_mismatch"):
            self.call()
        self.new.write_text("print('candidate')\n", encoding="utf-8")
        self.manifest = {**self.manifest, "trusted": True}
        with self.assertRaises(ValueError):
            self.call()
        self.assertEqual(slot.load_state(self.root), self.old_state)

    def test_unverified_old_slot_or_existing_pending_update_blocks(self):
        (self.root / "slot-A" / "recovery_one_probe.py").write_text("corrupted")
        with self.assertRaisesRegex(ValueError, "active_recovery_slot_unhealthy"):
            self.call()
        with self.assertRaises(ValueError):
            self.call(authority=None)
        # Explicit invalid verifier always fails before any candidate write.
        self.assertEqual(slot.load_state(self.root), self.old_state)

    def test_orphan_reservation_blocks_new_attempt(self):
        (self.root / "stage-reservation.lock").write_text("interrupted update")
        with self.assertRaises(FileExistsError):
            self.call()
        self.assertEqual(slot.load_state(self.root), self.old_state)
        self.assertFalse((self.root / "slot-B").exists())

    def test_existing_active_B_stages_only_A_if_A_is_not_lkg(self):
        first = self.call()
        self.assertEqual(first["slot"], "B")
        # The pending stage is not an authorization for activation.
        self.assertEqual(slot.load_state(self.root)["active"], "A")


if __name__ == "__main__":
    unittest.main()
