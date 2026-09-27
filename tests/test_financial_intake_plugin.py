import csv
import io
import unittest

from capabilities.financial_intake import (
    WintonExcelAdapter,
    canonical_from_invoice_payload,
)


class FinancialIntakePluginTests(unittest.TestCase):
    def test_winton_adapter_exports_review_free_invoice(self):
        doc = canonical_from_invoice_payload({
            "invoice_id": "inv-1",
            "status": "accepted",
            "engine": "rapidocr-template-v1+tesseract-fallback",
            "sha256": "abc",
            "fields": {
                "invoice_number": "AB12345678",
                "invoice_date": "2026-09-28",
                "seller_tax_id": "12345678",
                "vendor_name": "測試商號",
                "amount_before_tax": 1000,
                "tax_amount": 50,
                "total_amount": 1050,
            },
            "confidence": {"invoice_number": 0.99, "total_amount": 0.99},
        })
        result = WintonExcelAdapter().export(doc)
        self.assertEqual(result.adapter_id, "accounting.adapter.winton")
        self.assertTrue(result.requires_manual_import)
        rows = list(csv.reader(io.StringIO(result.payload.decode("utf-8-sig"))))
        self.assertEqual(rows[0][0], "發票號碼")
        self.assertEqual(rows[1][0], "AB12345678")
        self.assertIn("1050", rows[1])

    def test_review_required_document_cannot_export(self):
        for status in ("needs_review", "processing", "error"):
            with self.subTest(status=status):
                doc = canonical_from_invoice_payload({
                    "invoice_id": "inv-2",
                    "status": status,
                    "fields": {"invoice_number": "AB12345678"},
                })
                with self.assertRaises(ValueError):
                    WintonExcelAdapter().export(doc)

    def test_extracted_document_can_export(self):
        doc = canonical_from_invoice_payload({
            "invoice_id": "inv-ready",
            "status": "extracted",
            "fields": {"invoice_number": "AB12345678", "total_amount": 1050},
        })
        self.assertTrue(WintonExcelAdapter().can_export(doc))

    def test_batch_export_writes_one_header_and_multiple_rows(self):
        adapter = WintonExcelAdapter()
        docs = [
            canonical_from_invoice_payload({
                "invoice_id": "batch-1",
                "status": "reviewed",
                "fields": {"invoice_number": "AA12345678", "total_amount": 100},
            }),
            canonical_from_invoice_payload({
                "invoice_id": "batch-2",
                "status": "extracted",
                "fields": {"invoice_number": "BB87654321", "total_amount": 200},
            }),
        ]
        result = adapter.export_many(docs)
        rows = list(csv.reader(io.StringIO(result.payload.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][0], "AA12345678")
        self.assertEqual(rows[2][0], "BB87654321")

    def test_batch_export_is_all_or_nothing(self):
        adapter = WintonExcelAdapter()
        docs = [
            canonical_from_invoice_payload({
                "invoice_id": "batch-ok",
                "status": "reviewed",
                "fields": {"invoice_number": "AA12345678"},
            }),
            canonical_from_invoice_payload({
                "invoice_id": "batch-blocked",
                "status": "needs_review",
                "fields": {"invoice_number": "BB87654321"},
            }),
        ]
        with self.assertRaises(ValueError):
            adapter.export_many(docs)

    def test_canonical_model_has_no_winton_specific_fields(self):
        doc = canonical_from_invoice_payload({
            "invoice_id": "inv-3",
            "status": "accepted",
            "fields": {"invoice_number": "AB12345678"},
        })
        self.assertNotIn("winton", doc.fields)
        self.assertEqual(doc.schema, "financial-document.normalized/v1")


if __name__ == "__main__":
    unittest.main()
