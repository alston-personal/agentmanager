import unittest
from scripts.persona_gui_identity_gate import evaluate

class TestIdentityGate(unittest.TestCase):
    def test_missing_identity_blocks(self):
        r=evaluate({"account":"mio.milkcat","page_url":"https://www.threads.com/","rows":[]})
        self.assertEqual(r["reason"],"IDENTITY_NOT_VERIFIED")
        self.assertFalse(r["write_allowed"])
    def test_wrong_account_blocks(self):
        r=evaluate({"account":"oursong_alstonhuang","page_url":"https://www.threads.com/",
                    "identity_receipt":{"ok":True,"account":"oursong_alstonhuang","receipt_id":"a"},
                    "read_receipt":{"ok":True,"account":"oursong_alstonhuang","operation":"for_you.read","receipt_id":"b"},
                    "rows":[]})
        self.assertEqual(r["reason"],"ACCOUNT_MISMATCH")
    def test_verified_snapshot_only_yields_candidates(self):
        r=evaluate({"account":"mio.milkcat","page_url":"https://www.threads.com/",
                    "identity_receipt":{"ok":True,"account":"mio.milkcat","receipt_id":"a"},
                    "read_receipt":{"ok":True,"account":"mio.milkcat","operation":"for_you.read","receipt_id":"b"},
                    "rows":[{"url":"https://www.threads.com/@other/post/Abcd1234"}]})
        self.assertTrue(r["identity_gate_verified"])
        self.assertEqual(r["status"],"UNVERIFIED")
        self.assertEqual(r["candidate_count"],1)
        self.assertFalse(r["write_allowed"])
if __name__=="__main__": unittest.main()
