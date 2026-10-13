import unittest
from scripts.persona_for_you_observation import project_for_you_snapshot

class ForYouTests(unittest.TestCase):
    def setUp(self):
        self.kw=dict(account="mio.milkcat",page_url="https://www.threads.com/",
            identity_receipt={"ok":True,"account":"mio.milkcat","receipt_id":"identity1"},
            read_receipt={"ok":True,"account":"mio.milkcat","operation":"for_you.read","receipt_id":"read1"},
            rows=[{"url":"https://www.threads.com/@stranger/post/Abc123"}])
    def test_only_url_candidates_no_reply(self):
        r=project_for_you_snapshot(**self.kw)
        self.assertEqual(r["status"],"UNVERIFIED")
        self.assertEqual(r["candidate_count"],1)
        self.assertFalse(r["items"][0]["content_verified"])
        self.assertFalse(r["reply_allowed"])
        self.assertFalse(r["ir_revision_required"])
    def test_wrong_account_blocked(self):
        self.kw["account"]="oursong_alstonhuang"
        self.assertEqual(project_for_you_snapshot(**self.kw)["reason"],"ACCOUNT_MISMATCH")
    def test_missing_identity_proof_blocked(self):
        self.kw["identity_receipt"]={"ok":True}
        self.assertEqual(project_for_you_snapshot(**self.kw)["reason"],"IDENTITY_NOT_VERIFIED")
    def test_read_receipt_must_match_account_and_operation(self):
        self.kw["read_receipt"]["operation"]="post.read"
        self.assertEqual(project_for_you_snapshot(**self.kw)["reason"],"READ_RECEIPT_NOT_VERIFIED")
    def test_not_for_you_blocked(self):
        self.kw["page_url"]="https://www.threads.com/messages"
        self.assertEqual(project_for_you_snapshot(**self.kw)["reason"],"NOT_FOR_YOU_PAGE")
    def test_external_urls_only(self):
        self.kw["rows"]=[{"url":"https://www.threads.com/@mio.milkcat/post/Own1"},
            {"url":"https://evil.example/@stranger/post/X"},
            {"url":"https://www.threads.com/@stranger/post/Abc123"},
            {"url":"https://www.threads.com/@stranger/post/Abc123"}]
        self.assertEqual(project_for_you_snapshot(**self.kw)["candidate_count"],1)
    def test_large_scan_rejected(self):
        self.kw["rows"]=[{}]*21
        self.assertEqual(project_for_you_snapshot(**self.kw)["reason"],"BOUNDS_INVALID")
if __name__ == "__main__":
    unittest.main()
