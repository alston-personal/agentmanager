from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/windows/recovery_slot_runner.py"
spec = importlib.util.spec_from_file_location("recovery_slot_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RecoverySlotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "recovery"
        self.initial = Path(self.tmp.name) / "original.py"
        self.initial.write_text("print('old recovery')\n", encoding="utf-8")

    def state(self):
        return runner.load_state(self.root)

    def test_bootstrap_A_and_no_normal_reinstall_overwrite(self):
        first = runner.bootstrap(self.root, self.initial)
        self.assertEqual(first["active"], "A")
        self.assertEqual(first["last_known_good"], "A")
        self.assertIsNone(first["pending"])
        path = self.root / "slot-A" / "recovery_one_probe.py"
        self.assertTrue(runner.valid_slot(self.root, first, "A"))
        self.initial.write_text("print('new unsafe recovery')\n")
        self.assertEqual(runner.bootstrap(self.root, self.initial), first)
        self.assertEqual(path.read_text(), "print('old recovery')\n")

    def test_corrupted_active_stable_slot_fails_closed_without_flipping(self):
        runner.bootstrap(self.root, self.initial)
        (self.root / "slot-A" / "recovery_one_probe.py").write_text("tampered")
        with self.assertRaisesRegex(RuntimeError, "recovery_active_corrupt"):
            runner.run(self.root, "config.json", "status.json")
        self.assertEqual(self.state()["active"], "A")

    def test_pending_corrupt_B_cannot_bypass_authorized_rollback(self):
        runner.bootstrap(self.root, self.initial)
        b_path = self.root / "slot-B" / "recovery_one_probe.py"
        b_path.parent.mkdir()
        b_path.write_text("candidate", encoding="utf-8")
        state = self.state()
        runner.atomic_json(self.root / "slots.json", {
            **state, "active": "B", "last_known_good": "A",
            "pending": "B", "digests": {**state["digests"], "B": runner.digest(b_path)},
        })
        b_path.write_text("candidate-corrupt", encoding="utf-8")
        prior_bytes = (self.root / "slots.json").read_bytes()
        with patch.object(runner.subprocess, "run") as execute:
            with self.assertRaisesRegex(RuntimeError, "rollback_authority_required"):
                runner.run(self.root, "config.json", "status.json")
            execute.assert_not_called()
        self.assertEqual((self.root / "slots.json").read_bytes(), prior_bytes)
        preserved = self.state()
        self.assertEqual(preserved["active"], "B")
        self.assertEqual(preserved["pending"], "B")
        self.assertEqual(preserved["last_known_good"], "A")

    def test_pending_corrupt_B_can_still_probe_LKG_without_mutating_slots(self):
        runner.bootstrap(self.root, self.initial)
        b_path = self.root / "slot-B" / "recovery_one_probe.py"
        b_path.parent.mkdir()
        b_path.write_text("candidate", encoding="utf-8")
        state = self.state()
        runner.atomic_json(self.root / "slots.json", {
            **state, "active": "B", "last_known_good": "A",
            "pending": "B", "digests": {**state["digests"], "B": runner.digest(b_path)},
        })
        b_path.write_text("candidate-corrupt", encoding="utf-8")
        original = (self.root / "slots.json").read_bytes()
        with patch.object(runner.subprocess, "run") as execute:
            execute.return_value.returncode = 0
            with self.assertRaisesRegex(RuntimeError, "rollback_authority_required"):
                runner.run(self.root, "cfg.json", self.root / "status.json",
                           diagnose_lkg=True)
            self.assertEqual(execute.call_count, 1)
            self.assertIn("slot-A", execute.call_args.args[0][2])
            self.assertIn("lkg-diagnostic.json", execute.call_args.args[0][-1])
        report = json.loads((self.root / "lkg-rescue-diagnostic.json").read_text())
        self.assertEqual(report["schema"], "agentos.recovery-lkg-diagnostic/v1")
        self.assertEqual(report["result"], "ONE_PROBE_SUCCEEDED")
        self.assertFalse(report["rollback_authorized"])
        self.assertFalse(report["rollback_performed"])
        self.assertFalse(report["one_receipt_attested"])
        active = json.loads((self.root / "status.json").read_text())
        self.assertFalse(active["one_transport_roundtrip"])
        self.assertEqual(active["error_class"], "PendingRecoveryCandidateCorrupt")
        self.assertEqual((self.root / "slots.json").read_bytes(), original)

    def test_lkg_diagnostic_failure_never_claims_recovery_or_receipt(self):
        runner.bootstrap(self.root, self.initial)
        b_path = self.root / "slot-B" / "recovery_one_probe.py"
        b_path.parent.mkdir()
        b_path.write_text("candidate", encoding="utf-8")
        original = self.state()
        runner.atomic_json(self.root / "slots.json", {
            **original, "active": "B", "last_known_good": "A", "pending": "B",
            "digests": {**original["digests"], "B": runner.digest(b_path)},
        })
        b_path.write_text("corrupt", encoding="utf-8")
        original_bytes = (self.root / "slots.json").read_bytes()
        with patch.object(runner.subprocess, "run") as execute:
            execute.return_value.returncode = 1
            with self.assertRaisesRegex(RuntimeError, "rollback_authority_required"):
                runner.run(self.root, "cfg.json", self.root / "status.json",
                           diagnose_lkg=True)
        report = json.loads((self.root / "lkg-rescue-diagnostic.json").read_text())
        self.assertEqual(report["result"], "ONE_PROBE_FAILED")
        self.assertFalse(report["rollback_performed"])
        self.assertEqual((self.root / "slots.json").read_bytes(), original_bytes)

    def test_symlinked_slot_directory_does_not_count_as_healthy(self):
        runner.bootstrap(self.root, self.initial)
        stable = self.root / "slot-A"
        relocated = self.root / "slot-A-relocated"
        stable.rename(relocated)
        stable.symlink_to(relocated, target_is_directory=True)
        self.assertFalse(runner.valid_slot(self.root, self.state(), "A"))
        with self.assertRaisesRegex(RuntimeError, "recovery_active_corrupt"):
            runner.run(self.root, "config.json", "status.json")

    def test_pending_candidate_failure_does_not_auto_switch_on_network_error(self):
        runner.bootstrap(self.root, self.initial)
        b_path = self.root / "slot-B" / "recovery_one_probe.py"
        b_path.parent.mkdir()
        b_path.write_text("candidate", encoding="utf-8")
        state = self.state()
        runner.atomic_json(self.root / "slots.json", {
            **state, "active": "B", "last_known_good": "A",
            "pending": "B", "digests": {**state["digests"], "B": runner.digest(b_path)},
        })
        with patch.object(runner.subprocess, "run") as execute:
            execute.return_value.returncode = 1
            self.assertEqual(runner.run(self.root, "config.json", "status.json"), 1)
            self.assertIn("slot-B", execute.call_args.args[0][2])
        self.assertEqual(self.state()["active"], "B")

    def test_reject_unprotected_pending_and_missing_digest(self):
        runner.bootstrap(self.root, self.initial)
        state = self.state()
        for invalid in (
            {**state, "pending": "A"},
            {**state, "digests": {}},
            {**state, "active": "../A"},
            {**state, "digests": {"A": "a"*64, "C": "b"*64}},
        ):
            runner.atomic_json(self.root / "slots.json", invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.state()

    def test_refuses_unmanaged_slots_and_keeps_status_outside_slot(self):
        (self.root / "slot-A").mkdir(parents=True)
        (self.root / "slot-A" / "recovery_one_probe.py").write_text("unmanaged")
        with self.assertRaisesRegex(ValueError, "unmanaged_recovery_slot"):
            runner.bootstrap(self.root, self.initial)


if __name__ == "__main__":
    unittest.main()
