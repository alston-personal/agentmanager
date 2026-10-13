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

    def test_optional_multiview_is_not_approval(self):
        kwargs=dict(garment_id="shoe",target_layer="shoes",
                    source_fingerprint=sha256(b"source").hexdigest(),
                    isolated_image=None,mask=None,attributes={"color":"white"},
                    must_keep=["shoe upper"],extraction_backend="target-mask")
        empty=module.candidate_receipt(**kwargs)
        self.assertEqual(empty["productIR"]["views"],[])
        self.assertFalse(empty["approved"])
        view={"angle":"side","sourceType":"official_photo",
              "assetSha256":sha256(b"photo").hexdigest(),"verified":True}
        row=module.candidate_receipt(**kwargs,views=[view])
        self.assertEqual(row["productIR"]["views"],[view])
        self.assertEqual(row["productIR"]["multiviewStatus"],"pending_cross_view_review")
        with self.assertRaisesRegex(ValueError,"generated reference"):
            module.candidate_receipt(**kwargs,views=[dict(view,sourceType="generated_reference")])

if __name__ == "__main__":
    unittest.main()
