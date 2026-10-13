import unittest
from scripts.check_continuation_cutover_receipt import FIELDS, assess

class CutoverEvidenceTests(unittest.TestCase):
    def test_empty_fails_closed(self):
        self.assertIn("action_receipt_id", assess({}))
        self.assertIn("review_approval", assess({}))

    def test_same_generation_is_rejected(self):
        receipt = {key: "example" for key in FIELDS}
        receipt.update(pr="1923", pre_generation="g1", post_generation="g1")
        self.assertIn("generation_must_advance", assess(receipt))

    def test_rejects_placeholder_review_and_malformed_hashes(self):
        receipt = {key: "example" for key in FIELDS}
        receipt.update(pr="1923", pre_generation="g1", post_generation="g2")
        result = assess(receipt)
        self.assertIn("review_approval_placeholder", result)
        self.assertIn("runtime_release_sha_invalid_format", result)
        self.assertIn("readback_execution_sha256_invalid_format", result)

    def test_complete_manifest_is_only_structurally_valid(self):
        receipt = {key: "sample-actual-value" for key in FIELDS}
        receipt.update(pr="1923", pre_generation="g1", post_generation="g2",\n                       runtime_release_sha="a"*40, readback_execution_sha256="b"*64,\n                       readback_continuity_sha256="c"*64, review_approval="review-id-123")
        self.assertEqual([], assess(receipt))

if __name__ == "__main__":
    unittest.main()
