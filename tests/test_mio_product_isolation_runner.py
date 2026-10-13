import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("runner", SCRIPTS / "run_mio_product_isolation.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class CandidateRunnerTests(unittest.TestCase):
    def test_candidate_receipt_never_auto_approved(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            job_dir = root / "isolation_jobs"
            job_dir.mkdir()
            (job_dir / "top1.json").write_text(json.dumps({
                "schema": "agentos.wardrobe-isolation-job/v1",
                "garmentId": "top1", "state": "pending", "targetLayer": "upper_main",
                "sourceFingerprint": "a" * 64, "productName": "Test shirt"
            }))
            img = Image.new("RGB", (300, 300), "white")
            for x in range(90, 190):
                for y in range(75, 230):
                    img.putpixel((x, y), (40, 70, 100))
            source = root / "source.png"
            img.save(source)
            with patch.object(runner, "ROOT", root):
                receipt = runner.run("top1", source)
            self.assertEqual(receipt["state"], "candidate")
            self.assertFalse(receipt["approved"])
            snapshot = pathlib.Path(receipt["sourceSnapshot"])
            self.assertTrue(snapshot.is_file())
            self.assertEqual(snapshot.read_bytes(), source.read_bytes())
            self.assertEqual(receipt["targetMatchEvidence"]["status"], "unverified")
            self.assertTrue(pathlib.Path(receipt["isolatedAsset"]).exists())
            self.assertTrue(pathlib.Path(receipt["maskAsset"]).exists())
            self.assertTrue((root / "isolation_candidates" / "top1" / receipt["sourceAssetSha256"] / "candidate-receipt.json").exists())

    def test_approved_job_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            job_dir = root / "isolation_jobs"
            job_dir.mkdir()
            (job_dir / "approved.json").write_text(json.dumps({
                "schema": "agentos.wardrobe-isolation-job/v1",
                "garmentId": "approved", "state": "approved"
            }))
            with patch.object(runner, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "immutable"):
                    runner.run("approved", root / "anything.png")

if __name__ == "__main__":
    unittest.main()
