"""Receipt integration tests using existing ControlPlaneStore."""
import json
import tempfile
import unittest
from pathlib import Path
from agent_core.control_plane import ControlPlaneStore
from agent_core.bounty_probe_receipt import reconcile_probe_receipt


class ProbeReceiptIntegrationTests(unittest.TestCase):
    def test_auth_required_is_durable_failed_probe_not_bounty_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            task = store.submit_task("github.repo.read", {"repo":"a/b"}, "bounty-probe-403")
            receipt = Path(folder) / "receipt.json"
            receipt.write_text(json.dumps({"capability":"github.repo.read","repository":"a/b",
                "outcome":"AUTH_REQUIRED","http_status":403,"reason":"permission_denied"}))
            updated = reconcile_probe_receipt(store, task["taskId"], receipt)
            self.assertEqual(updated["status"], "failed")
            self.assertEqual(updated["result"]["outcome"], "AUTH_REQUIRED")
            self.assertFalse(updated["result"]["bountyDelivered"])
            self.assertFalse(updated["result"]["upstreamWriteVerified"])

    def test_ready_is_only_read_probe_success(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            task = store.submit_task("github.repo.read", {"repo":"a/b"}, "bounty-probe-200")
            receipt = Path(folder) / "receipt.json"
            receipt.write_text(json.dumps({"capability":"github.repo.read","repository":"a/b",
                "outcome":"READY","http_status":200,"reason":"permission_probe_passed"}))
            updated = reconcile_probe_receipt(store, task["taskId"], receipt)
            self.assertEqual(updated["status"], "succeeded")
            self.assertFalse(updated["result"]["bountyDelivered"])

    def test_unverified_never_counts_as_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ControlPlaneStore(Path(folder) / "control.sqlite3")
            task = store.submit_task("github.repo.read", {}, "probe-dryrun")
            receipt = Path(folder) / "receipt.json"
            receipt.write_text(json.dumps({"capability":"github.repo.read","repository":"a/b",
                "outcome":"UNVERIFIED","http_status":None,"reason":"dry_run"}))
            updated = reconcile_probe_receipt(store, task["taskId"], receipt)
            self.assertEqual(updated["status"], "failed")


if __name__ == "__main__":
    unittest.main()
