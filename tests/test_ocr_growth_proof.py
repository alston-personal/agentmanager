import tempfile
import unittest
from pathlib import Path

from agent_core.ocr_growth_proof import BENCHMARK_SCHEMA, run_ocr_growth_proof


class OCRGrowthProofTests(unittest.TestCase):
    def _manifest(self):
        return {
            "schema": BENCHMARK_SCHEMA,
            "proof_id": "test-ocr-memory-g3",
            "controlled_variables": {
                "ocr_observation": "captured-and-held-constant",
                "evaluation": "exact-field-match+review-classification",
            },
            "learning_events": [
                {
                    "id": "learn-1",
                    "candidate_id": "vendor-name-good-day-food",
                    "source_case_id": "training-invoice-1",
                    "field_name": "vendor_name",
                    "observed_value": "好日子食晶有限公司",
                    "corrected_value": "好日子食品有限公司",
                    "confirmations": 2,
                    "context": {
                        "template_id": "three_part_uniform_invoice",
                        "entity_id": "16908319",
                    },
                }
            ],
            "heldout": [
                {
                    "id": "heldout-invoice-2",
                    "context": {
                        "template_id": "three_part_uniform_invoice",
                        "entity_id": "16908319",
                    },
                    "baseline_fields": {
                        "invoice_number": "AB12345678",
                        "invoice_date": "2026-10-05",
                        "vendor_name": "好日子食晶有限公司",
                        "seller_tax_id": "16908319",
                        "amount_before_tax": 1000,
                        "tax_amount": 50,
                        "total_amount": 1050,
                    },
                    "baseline_confidence": {
                        "invoice_number": 0.99,
                        "invoice_date": 0.99,
                        "vendor_name": 0.78,
                        "seller_tax_id": 0.99,
                        "amount_before_tax": 0.99,
                        "tax_amount": 0.99,
                        "total_amount": 0.99,
                    },
                    "expected": {
                        "invoice_number": "AB12345678",
                        "invoice_date": "2026-10-05",
                        "vendor_name": "好日子食品有限公司",
                        "seller_tax_id": "16908319",
                        "amount_before_tax": 1000,
                        "tax_amount": 50,
                        "total_amount": 1050,
                    },
                }
            ],
        }

    def test_counterfactual_replay_reaches_g3(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = run_ocr_growth_proof(self._manifest(), workdir=Path(tmp))
        self.assertEqual(receipt["verdict"], "G3")
        self.assertEqual(receipt["baseline"]["correct_fields"], 6)
        self.assertEqual(receipt["experienced"]["correct_fields"], 7)
        self.assertGreater(receipt["uplift"]["field_accuracy_absolute"], 0)
        self.assertEqual(receipt["experienced"]["memory_reuse_hits"], 1)
        self.assertEqual(receipt["regressions"]["false_auto_corrections"], 0)
        self.assertEqual(receipt["regressions"]["correct_to_wrong"], 0)
        self.assertEqual(receipt["rows"][0]["baseline"]["review_status"], "quick_confirm")
        self.assertEqual(receipt["rows"][0]["experienced"]["review_status"], "extracted")

    def test_rejects_learning_heldout_leakage(self):
        manifest = self._manifest()
        manifest["learning_events"][0]["source_case_id"] = "heldout-invoice-2"
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "held-out leakage"):
                run_ocr_growth_proof(manifest, workdir=Path(tmp))

    def test_false_auto_correction_blocks_g3(self):
        manifest = self._manifest()
        manifest["heldout"][0]["expected"]["vendor_name"] = "另一家公司"
        with tempfile.TemporaryDirectory() as tmp:
            receipt = run_ocr_growth_proof(manifest, workdir=Path(tmp))
        self.assertEqual(receipt["verdict"], "NOT_G3")
        self.assertEqual(receipt["regressions"]["false_auto_corrections"], 1)


if __name__ == "__main__":
    unittest.main()
