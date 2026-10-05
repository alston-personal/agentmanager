import unittest

from services.invoice_intake.invoice_core import (
    choose_amounts,
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
