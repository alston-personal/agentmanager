import unittest
from datetime import datetime, timezone
from scripts.persona_public_discovery_contract import project_public_candidates

NOW = datetime(2026, 10, 12, 3, 0, tzinfo=timezone.utc)
SOURCE = {"ok": True, "operation": "public.feed.read", "account": "mio.milkcat", "receipt_id": "read-1"}
POST = {"id": "123", "root_id": "123", "username": "friend", "timestamp": "2026-10-12T02:00:00+0000", "text": "Interesting public post", "visibility": "public"}

class PublicDiscoveryContractTests(unittest.TestCase):
    def read(self, rows=None, source=None, **other):
        return project_public_candidates(rows=[POST] if rows is None else rows,
            source_receipt=SOURCE if source is None else source, account="mio.milkcat", now=NOW, **other)

    def test_verified_public_read_has_no_write_authority(self):
        report = self.read()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["items"][0]["decision"], "UNDECIDED")
        self.assertFalse(report["write_allowed"])
        self.assertFalse(report["items"][0]["reply_allowed"])

    def test_denies_old_owned_private_and_duplicate_posts(self):
        rows = [POST, POST, {**POST, "id": "124", "visibility": "private"},
                {**POST, "id": "125", "username": "mio.milkcat"},
                {**POST, "id": "126", "timestamp": "2026-10-01T00:00:00Z"}]
        report = self.read(rows)
        self.assertEqual(len(report["items"]), 1)
        self.assertEqual(report["rejected_count"], 4)

    def test_account_isolation(self):
        report = self.read(source={**SOURCE, "account": "oursong_alstonhuang"})
        self.assertEqual(report["reason"], "ACCOUNT_MISMATCH")
        self.assertEqual(report["items"], [])

    def test_owned_post_read_is_not_public_discovery(self):
        report = self.read(source={**SOURCE, "operation": "post.read"})
        self.assertEqual(report["reason"], "PUBLIC_ADAPTER_REQUIRED")

    def test_unverified_source_blocks(self):
        report = self.read(source={**SOURCE, "ok": False})
        self.assertEqual(report["status"], "BLOCKED")

    def test_missing_receipt_blocks(self):
        report = self.read(source={**SOURCE, "receipt_id": None})
        self.assertEqual(report["reason"], "RECEIPT_MISSING")

    def test_seen_cursor(self):
        report = self.read(seen=["123"])
        self.assertEqual(report["items"], [])

    def test_bounded(self):
        with self.assertRaises(ValueError):
            self.read(rows=[POST] * 31)

    def test_rejects_naive_time(self):
        self.assertEqual(self.read(rows=[{**POST, "timestamp": "2026-10-12T02:00:00"}])["items"], [])

    def test_does_not_echo_untrusted_metadata(self):
        report = self.read(rows=[{**POST, "secret": "TOKEN", "text": "x" * 1000}])
        self.assertNotIn("TOKEN", str(report))
        self.assertEqual(len(report["items"][0]["text_excerpt"]), 500)


    def test_post_read_is_exact_object_bound(self):
        receipt = {**SOURCE, "operation": "public.post.read", "object_id": "999"}
        self.assertEqual(self.read(source=receipt)["reason"], "OBJECT_ID_MISMATCH")
        receipt["object_id"] = "123"
        self.assertEqual(len(self.read(source=receipt)["items"]), 1)

    def test_post_read_rejects_batch(self):
        receipt = {**SOURCE, "operation": "public.post.read", "object_id": "123"}
        self.assertEqual(self.read(rows=[POST, POST], source=receipt)["reason"], "OBJECT_ID_MISMATCH")

    def test_invalid_clock_window_and_cursor(self):
        for hours in (-1, 0, float("nan"), float("inf"), 169):
            with self.subTest(hours=hours), self.assertRaises(ValueError):
                self.read(max_age_hours=hours)
        with self.assertRaises(ValueError):
            self.read(seen=["x"] * 5001)

    def test_missing_reader_identity(self):
        self.assertEqual(self.read(source={**SOURCE, "account": None})["reason"], "ACCOUNT_MISMATCH")

if __name__ == "__main__":
    unittest.main()
