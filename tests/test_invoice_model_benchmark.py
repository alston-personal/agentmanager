import unittest
from scripts import invoice_model_benchmark as bench


class InvoiceModelBenchmarkTests(unittest.TestCase):
    def test_money_score_is_reported_separately(self):
        expected = {
            "invoice_number": "EC55544057",
            "seller_tax_id": "16672215",
            "amount_before_tax": 24500,
            "tax_amount": 1225,
            "total_amount": 25725,
        }
        actual = {
            "invoice_number": "EC55544057",
            "seller_tax_id": "16672215",
            "amount_before_tax": None,
            "tax_amount": None,
            "total_amount": None,
        }
        scored = bench.score(expected, actual)
        self.assertEqual(scored["correct"], 2)
        self.assertEqual(scored["total"], 5)
        self.assertEqual(scored["money_correct"], 0)
        self.assertEqual(scored["money_total"], 3)
        self.assertEqual(scored["money_exact_match"], 0.0)

    def test_structured_score_normalizes_spacing_and_commas(self):
        expected = {"invoice_number": "EC55544057", "total_amount": 25725}
        actual = {"invoice_number": "EC 55544057", "total_amount": 25725}
        scored = bench.score(expected, actual)
        self.assertEqual(scored["field_exact_match"], 1.0)
        self.assertEqual(scored["money_exact_match"], 1.0)

    def test_rapidocr_score_checks_visible_evidence_without_structured_claim(self):
        expected = {
            "invoice_number": "EC55544057",
            "invoice_date": "2026-09-25",
            "amount_before_tax": 24500,
            "tax_amount": 1225,
            "total_amount": 25725,
        }
        actual = {
            "_raw_text": "EC55544057\n115 09 25\n24500\n1225\n25725",
        }
        scored = bench.rapidocr_score(expected, actual)
        self.assertEqual(scored["field_exact_match"], 1.0)
        self.assertEqual(scored["money_exact_match"], 1.0)
        self.assertIsNone(scored["checks"]["total_amount"]["actual"])


if __name__ == "__main__":
    unittest.main()
