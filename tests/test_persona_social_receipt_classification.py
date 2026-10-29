import unittest
from scripts.persona_social_receipt_classification import classify


class SocialReceiptClassificationTest(unittest.TestCase):
    def test_held_readback_is_not_a_fatal_runtime_error(self):
        r = {"status":"RECONCILIATION_PENDING","readback_status":"NOT_OBSERVED",
             "delivery_confirmed":False,"write_performed":False}
        self.assertEqual(classify(r),"PENDING_READBACK")

    def test_confirmed_reconciled_reply(self):
        self.assertEqual(classify({"status":"RECONCILED","delivery_confirmed":True}),"PASS")
        self.assertEqual(classify({"status":"RECONCILED","delivery_confirmed":False}),"BLOCKED")

    def test_unknown_or_unconfirmed_write_never_passes(self):
        self.assertEqual(classify({"status":"WRITE_OUTCOME_UNKNOWN"}),"WRITE_OUTCOME_UNKNOWN")
        self.assertEqual(classify({"status":"BLOCKED","ok":False}),"BLOCKED")
        with self.assertRaises(ValueError):
            classify({"status":"SUCCESS"})


if __name__=="__main__":
    unittest.main()
