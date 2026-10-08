import importlib.util
import pathlib
import tempfile
import unittest
from hashlib import sha256

P = pathlib.Path(__file__).resolve().parents[1] / "scripts/mio_isolation_candidate_receipt.py"
spec = importlib.util.spec_from_file_location("isolation_candidate_receipt", P)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ReceiptTests(unittest.TestCase):
    def test_candidate_is_not_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "isolated.png"
            mask = pathlib.Path(directory) / "mask.png"
            source.write_bytes(b"x" * 1500)
            mask.write_bytes(b"y" * 200)
            row = module.candidate_receipt(
                garment_id="top-1", target_layer="upper_main",
                source_fingerprint=sha256(b"source").hexdigest(),
                isolated_image=source, mask=mask,
                attributes={"neckline": "square"}, must_keep=["square neckline"],
                extraction_backend="segmenter-v1", target_match_evidence={"confidence": 0.99},
            )
            self.assertEqual(row["state"], "candidate")
            self.assertFalse(row["approved"])
            self.assertEqual(row["review"]["state"], "pending")
    def test_missing_mask_needs_review(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "isolated.png"
            source.write_bytes(b"x" * 1500)
            row = module.candidate_receipt(
                garment_id="top-1", target_layer="upper_main",
                source_fingerprint=sha256(b"source").hexdigest(),
                isolated_image=source, mask=None, attributes={"color": "brown"},
                must_keep=["brown"], extraction_backend="simple-bg-remove",
            )
            self.assertEqual(row["state"], "needs_review")
            self.assertFalse(row["approved"])

if __name__ == "__main__":
    unittest.main()
