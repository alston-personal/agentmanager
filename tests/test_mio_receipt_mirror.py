import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.bootstrap_control import (
    ACTION_PUBLISH_MIO_APPROVED,
    _mirror_mio_receipt,
)


class MioReceiptMirrorTests(unittest.TestCase):
    KEY = "mio-post-20260922-small-discoveries-v1"
    ID = "18356065492302036"
    URL = "https://www.threads.com/@sunlake.milkcat/post/DdgAUKMlH-X"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"AGENTOS_MIO_RECEIPT_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def receipt(self, status="PASS", ok=True, url=None):
        lines = [
            "galaxy_day1_publish=" + status,
            "galaxy_day1_object_id=" + self.ID,
            "galaxy_day1_permalink=" + (self.URL if url is None else url),
            "galaxy_day1_username=sunlake.milkcat",
        ]
        return {
            "action": ACTION_PUBLISH_MIO_APPROVED,
            "request_id": "sample-1",
            "source_commit": "a" * 40,
            "completed_at": "2026-09-22T00:00:00Z",
            "ok": ok,
            "steps": [{"stdout": "\n".join(lines), "stderr": "access_token=do-not-store"}],
        }

    def record(self):
        return Path(self.tmp.name) / (self.KEY + ".json")

    def test_verified_success_is_persisted_without_secrets(self):
        _mirror_mio_receipt(self.receipt(), self.KEY)
        row = json.loads(self.record().read_text())
        self.assertEqual(row["platform_object_id"], self.ID)
        self.assertEqual(row["permalink"], self.URL)
        self.assertNotIn("access_token", self.record().read_text())
        self.assertEqual(self.record().stat().st_mode & 0o777, 0o600)

    def test_already_present_is_persisted(self):
        _mirror_mio_receipt(self.receipt("ALREADY_PRESENT"), self.KEY)
        self.assertEqual(json.loads(self.record().read_text())["publish_status"], "ALREADY_PRESENT")

    def test_failed_or_unverified_do_not_persist(self):
        for receipt in (self.receipt(ok=False), self.receipt("FAIL"), self.receipt(url="not-a-threads-url")):
            _mirror_mio_receipt(receipt, self.KEY)
            self.assertFalse(self.record().exists())

    def test_same_post_is_idempotent_and_conflict_is_detected(self):
        _mirror_mio_receipt(self.receipt(), self.KEY)
        _mirror_mio_receipt(self.receipt(), self.KEY)
        conflict = self.receipt()
        conflict["steps"][0]["stdout"] = conflict["steps"][0]["stdout"].replace(self.ID, "18356065492302037")
        with self.assertRaises(RuntimeError):
            _mirror_mio_receipt(conflict, self.KEY)
        self.assertEqual(json.loads(self.record().read_text())["platform_object_id"], self.ID)

    def test_unrelated_action_and_invalid_key_are_ignored(self):
        other = self.receipt()
        other["action"] = "agentos.transport.repair"
        _mirror_mio_receipt(other, self.KEY)
        _mirror_mio_receipt(self.receipt(), "../bad")
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
