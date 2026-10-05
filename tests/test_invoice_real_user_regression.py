import unittest

from services.invoice_intake.invoice_core import (
    choose_amounts,
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
