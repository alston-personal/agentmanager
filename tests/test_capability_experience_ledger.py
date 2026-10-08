import tempfile
import unittest
from pathlib import Path
from scripts.capability_experience_ledger import record

class ExperienceLedgerTests(unittest.TestCase):
    def test_source_code_cannot_claim_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                record({"capability":"image.edit.flux","evidence_kind":"source_code",
                        "source_ref":"a.py","outcome":"VERIFIED_SUCCESS"},Path(temp)/"ledger.jsonl")

    def test_artifact_is_observed_not_provider_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger=Path(temp)/"ledger.jsonl"
            event={"capability":"mio.asset","evidence_kind":"git_artifact",
                   "source_ref":"commit:abc","outcome":"OUTPUT_OBSERVED"}
            self.assertEqual(record(event,ledger)["status"],"RECORDED")
            self.assertEqual(record(event,ledger)["status"],"DUPLICATE")

    def test_runtime_receipt_classification(self):
        from scripts.capability_experience_ledger import classify
        self.assertEqual(classify({"status":"GENERATED_UNVERIFIED","image_sha256":"a"*64}),"OUTPUT_OBSERVED")
        self.assertEqual(classify({"status":"BLOCKED"}),"FAILED")
        self.assertEqual(classify({"status":"EXECUTED","write_performed":True,
                                   "provider_receipt":{"ok":True}}),"VERIFIED_SUCCESS")

if __name__=="__main__":
    unittest.main()
