"""After-crash Realm binding assessment is strictly read-only and fail-closed."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/windows"))
from recovery_update_reconcile import reconcile_realm_transfer, REALM_TRANSFER_PENDING_SCHEMA

A = "realm-u-" + "a" * 24
B = "realm-u-" + "b" * 24


class RealmTransferReadOnlyTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name) / "AgentOS"
        self.state = self.root / "state"
        self.state.mkdir(parents=True)
        self.active = self.state / "client.json"
        self.source = b'{"node_id":"node-a","realm_id":"' + A.encode() + b'","node_token":"secret-A"}'
        self.target = b'{"node_id":"node-a","realm_id":"' + B.encode() + b'","node_token":"secret-B"}'
        self.active.write_bytes(self.source)
        self.pending = self.state / "realm-transfer-pending.json"

    def make_pending(self, **changes):
        data = dict(schema=REALM_TRANSFER_PENDING_SCHEMA,
                    transfer_id="1"*32, node_id="node-a",
                    source_realm_id=A, target_realm_id=B,
                    source_sha256=hashlib.sha256(self.source).hexdigest(),
                    target_sha256=hashlib.sha256(self.target).hexdigest(),
                    state="CUTOVER_UNRESOLVED")
        data.update(changes)
        self.pending.write_text(json.dumps(data))
        return data

    def check(self):
        return reconcile_realm_transfer(install_root=self.root, participant_id="node-a")

    def assert_frozen(self, result):
        self.assertFalse(result["activation_authorized"])
        self.assertFalse(result["rollback_authorized"])
        self.assertFalse(result["one_receipt_attested"])
        self.assertFalse(result["mutation_permitted"])
        self.assertNotIn("secret-A", json.dumps(result))
        self.assertNotIn("secret-B", json.dumps(result))

    def test_no_pending_never_grants_authority(self):
        before = self.active.read_bytes()
        result = self.check()
        self.assertEqual(result["classification"], "NO_PENDING_LOCAL_TRANSFER")
        self.assert_frozen(result)
        self.assertEqual(self.active.read_bytes(), before)

    def test_pre_cutover_crash(self):
        self.make_pending()
        before = self.active.read_bytes()
        result = self.check()
        self.assertEqual(result["classification"], "GOVERNED_SOURCE_BINDING_RECONCILIATION")
        self.assert_frozen(result)
        self.assertEqual(self.active.read_bytes(), before)
        self.assertTrue(self.pending.exists())

    def test_post_swap_crash_with_backup(self):
        self.make_pending()
        self.active.write_bytes(self.target)
        (self.state / ("client.realm-rollback-"+"1"*32+".json")).write_bytes(self.source)
        result = self.check()
        self.assertEqual(result["classification"], "GOVERNED_TARGET_BINDING_RECONCILIATION")
        self.assertEqual(result["source_backup_status"], "source_bytes_present")
        self.assert_frozen(result)
        self.assertEqual(self.active.read_bytes(), self.target)

    def test_corrupted_active_or_missing(self):
        self.make_pending()
        self.active.write_bytes(b"corruption")
        result = self.check()
        self.assertEqual(result["classification"], "HUMAN_REQUIRED_BINDING_DIVERGED")
        self.assert_frozen(result)
        self.active.unlink()
        self.assertEqual(self.check()["classification"], "HUMAN_REQUIRED_ACTIVE_BINDING_MISSING")

    def test_mismatched_node_and_self_authority_are_rejected(self):
        self.make_pending(node_id="other")
        with self.assertRaisesRegex(ValueError, "untrusted_pending"):
            self.check()
        self.make_pending(activation_authorized=True)
        # Locally asserted authorization is not a trusted ONE receipt.
        with self.assertRaisesRegex(ValueError, "untrusted_pending"):
            self.check()

    def test_bad_record_rejected_without_mutation(self):
        self.make_pending(source_sha256="not-a-digest")
        with self.assertRaisesRegex(ValueError, "untrusted_pending"):
            self.check()
        self.pending.write_text("{garbled")
        with self.assertRaisesRegex(ValueError, "invalid_pending"):
            self.check()

    def test_symlink_pending_refused(self):
        self.make_pending()
        alternate = self.state / "other.json"
        self.pending.rename(alternate)
        try:
            self.pending.symlink_to(alternate)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "indirect_realm"):
            self.check()


if __name__ == "__main__":
    unittest.main()
