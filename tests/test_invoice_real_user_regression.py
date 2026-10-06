import unittest
from pathlib import Path

from services.invoice_intake.invoice_core import (
    choose_amounts,
    classify_review,
    deep_fallback_enrich,
    extract_legacy_invoice,
    extract_line_items_from_text,
    normalize_vendor_name,
)


class InvoiceRealUserRegressionTests(unittest.TestCase):
    def test_vendor_name_from_company_line(self):
        text = """
        統一發票（三聯式）
        好日子食品有限公司
        統一編號 16908319
        """
        self.assertEqual(normalize_vendor_name(text), "好日子食品有限公司")

    def test_line_items_capture_description_quantity_unit_price_amount(self):
        text = """
        品名 數量 單價 金額
        加工費 2 500 1000
        材料費 3 200 600
        總計 1600
        """
        items = extract_line_items_from_text(text)
        self.assertEqual(
            [(x["description"], x["quantity"], x["unit_price"], x["amount"]) for x in items],
            [("加工費", 2, 500, 1000), ("材料費", 3, 200, 600)],
        )

    def test_line_items_reject_arithmetic_mismatch(self):
        self.assertEqual(extract_line_items_from_text("加工費 2 500 800"), [])

    def test_vendor_078_is_quick_confirm_not_full_review(self):
        fields = {
            "invoice_number": "AB12345678",
            "invoice_date": "2026-10-05",
            "vendor_name": "好日子食品有限公司",
            "seller_tax_id": "16908319",
            "amount_before_tax": 1000,
            "tax_amount": 50,
            "total_amount": 1050,
        }
        confidence = {
            "invoice_number": 0.95,
            "invoice_date": 0.90,
            "vendor_name": 0.78,
            "seller_tax_id": 0.88,
            "amount_before_tax": 0.98,
            "tax_amount": 0.98,
            "total_amount": 0.98,
        }
        review = classify_review(fields, confidence)
        self.assertEqual(review["status"], "quick_confirm")
        self.assertEqual(review["required_fields"], [])
        self.assertEqual(review["confirm_fields"], ["vendor_name"])

    def test_almost_empty_result_is_recognition_insufficient(self):
        fields = {
            "invoice_number": None,
            "invoice_date": None,
            "vendor_name": None,
            "seller_tax_id": None,
            "amount_before_tax": None,
            "tax_amount": None,
            "total_amount": 1050,
        }
        confidence = {key: 0.0 for key in fields}
        confidence["total_amount"] = 0.92
        review = classify_review(fields, confidence)
        self.assertEqual(review["status"], "recognition_insufficient")
        self.assertIn("recognition:insufficient_fields", review["reasons"])

    def test_missing_core_field_stays_needs_review(self):
        fields = {
            "invoice_number": None,
            "invoice_date": "2026-10-05",
            "vendor_name": "好日子食品有限公司",
            "seller_tax_id": "16908319",
            "amount_before_tax": 1000,
            "tax_amount": 50,
            "total_amount": 1050,
        }
        confidence = {key: 0.98 for key in fields}
        review = classify_review(fields, confidence)
        self.assertEqual(review["status"], "needs_review")
        self.assertIn("invoice_number", review["required_fields"])

    def test_confirmed_stamp_with_complete_high_confidence_can_extract(self):
        fields = {
            "invoice_number": "AB12345678",
            "invoice_date": "2026-10-05",
            "vendor_name": "好日子食品有限公司",
            "seller_tax_id": "16908319",
            "amount_before_tax": 1000,
            "tax_amount": 50,
            "total_amount": 1050,
        }
        confidence = {key: 0.99 for key in fields}
        review = classify_review(
            fields,
            confidence,
            stamp_recognition={"status": "MATCHED_CONFIRMED", "decision": "same_stamp"},
        )
        self.assertEqual(review["status"], "extracted")
        self.assertEqual(review["required_fields"], [])
        self.assertEqual(review["confirm_fields"], [])

    def test_two_stage_real_fixture_quality_is_monotonic(self):
        import json

        manifest = json.loads(
            Path("benchmarks/invoice_handwriting/public_cases.json").read_text()
        )
        fast_correct = 0
        deep_correct = 0
        checked = 0
        per_case = []

        for case in manifest["cases"]:
            data = Path(case["fixture_path"]).read_bytes()
            fast = extract_legacy_invoice(data)
            deep = deep_fallback_enrich(data, fast, budget_seconds=8)

            for key, expected in case["expected"].items():
                if key not in {
                    "invoice_number", "invoice_date", "seller_tax_id",
                    "amount_before_tax", "tax_amount", "total_amount",
                }:
                    continue
                checked += 1
                expected_norm = str(expected).replace(" ", "").upper()
                fast_value = fast.fields.get(key)
                deep_value = deep.fields.get(key)
                fast_ok = str(fast_value).replace(" ", "").upper() == expected_norm
                deep_ok = str(deep_value).replace(" ", "").upper() == expected_norm
                fast_correct += int(fast_ok)
                deep_correct += int(deep_ok)
                per_case.append(
                    (case["id"], key, fast_value, deep_value, expected, fast_ok, deep_ok)
                )

                if fast_ok:
                    self.assertEqual(
                        deep_value,
                        fast_value,
                        f"{case['id']}: deep fallback overwrote correct {key}",
                    )

        print(
            "two_stage_quality "
            f"fast={fast_correct}/{checked} deep={deep_correct}/{checked} "
            f"details={per_case}"
        )
        self.assertGreaterEqual(
            deep_correct,
            fast_correct,
            f"deep fallback reduced known-answer accuracy: {per_case}",
        )
        self.assertGreater(
            deep_correct,
            fast_correct,
            f"deep fallback did not recover any previously missed known field: {per_case}",
        )

    def test_amounts_recovered_from_scattered_numeric_ocr(self):
        texts = [
            "115 09 10\n16908319\nEC04593812",
            "銷售額\n1,000\n營業稅\n50\n總計\n1,050",
            "1000\n50\n1050",
        ]
        subtotal, tax, total, confidence = choose_amounts(texts)
        self.assertEqual((subtotal, tax, total), (1000, 50, 1050))
        self.assertGreaterEqual(confidence, 0.9)


if __name__ == "__main__":
    unittest.main()
