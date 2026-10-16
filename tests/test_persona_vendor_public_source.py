"""Contract tests for verified public permalink reads (no network / public write)."""
import unittest
from scripts.persona_vendor_public_source import validate_vendor_public_post


URL = "https://www.threads.com/@example.user/post/AbC123"
SOURCE = {"schema": "agentos.social.threads.public-post/v1",
          "source": {"url": URL, "username": "example.user", "text": "公開討論"},
          "login_bypass_used": False, "anti_bot_bypass_used": False}
RECEIPT = {"ok": True, "receipt_id": "oracle-read-001",
           "operation": "public.post.resolve", "url": URL}


class PublicReaderContractTest(unittest.TestCase):
    def project(self, response=None, receipt=None, requested_url=URL):
        return validate_vendor_public_post(
            requested_url=requested_url, response=response if response is not None else SOURCE,
            source_receipt=receipt if receipt is not None else RECEIPT,
            observed_at="2026-10-16T00:00:00Z")

    def test_verified_public_source(self):
        result = self.project()
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["reply_allowed"])
        self.assertEqual(result["items"][0]["text"], "公開討論")

    def test_no_receipt(self):
        self.assertEqual(self.project(receipt={})["reason"], "SOURCE_RECEIPT_REQUIRED")

    def test_receipt_url_mismatch(self):
        self.assertEqual(self.project(receipt={**RECEIPT, "url": "https://www.threads.com/@other/post/xyz"})["reason"], "RECEIPT_URL_MISMATCH")

    def test_source_mismatch(self):
        self.assertEqual(self.project(response={**SOURCE, "source": {**SOURCE["source"], "username": "other"}})["reason"], "AUTHOR_MISMATCH")

    def test_no_content(self):
        self.assertEqual(self.project(response={**SOURCE, "source": {**SOURCE["source"], "text": ""}})["reason"], "TEXT_INVALID")

    def test_no_bypass(self):
        self.assertEqual(self.project(response={**SOURCE, "anti_bot_bypass_used": True})["reason"], "READER_PROVENANCE_INVALID")

    def test_own_post(self):
        own = "https://www.threads.com/@mio.milkcat/post/AbC123"
        receipt = {**RECEIPT, "url": own}
        response = {**SOURCE, "source": {**SOURCE["source"], "url": own, "username": "mio.milkcat"}}
        self.assertEqual(self.project(response=response, receipt=receipt, requested_url=own)["reason"], "OWN_POST")


if __name__ == "__main__":
    unittest.main()
