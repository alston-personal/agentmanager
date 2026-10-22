"""Contract tests for GPT Web receipt ingestion boundary (no browser/DB writes)."""
import json
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from PIL import Image
from services.invoice_intake.invoice_core import InvoiceStore
from services.invoice_intake.gpt_web_provider import from_receipt

REQ = "invoice-roundtrip-my04200253-test"
DOC = {
    "agentos_request_id": REQ,
    "invoice_number": "MY04200253",
    "invoice_date": "2019-03-23",
    "seller_tax_id": "82328968",
    "total_amount": 50,
}


def receipt(doc=None, *, ok=True, request_id=REQ):
    return {
        "ok": ok,
        "result": {
            "request_id": request_id,
            "assistant_text": json.dumps(DOC if doc is None else doc),
        },
    }


class GPTWebInvoiceProviderTest(unittest.TestCase):
    def test_actual_fixture_fields_remain_and_review_required(self):
        result = from_receipt(receipt(), request_id=REQ)
        self.assertEqual(result["fields"]["invoice_number"], "MY04200253")
        self.assertEqual(result["fields"]["invoice_date"], "2019-03-23")
        self.assertEqual(result["fields"]["seller_tax_id"], "82328968")
        self.assertEqual(result["fields"]["total_amount"], 50)
        self.assertIsNone(result["fields"]["tax_amount"])
        self.assertIn("line_items", result["issues"])
        self.assertTrue(result["needs_review"])

    def test_failed_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, "RECEIPT_NOT_VERIFIED"):
            from_receipt(receipt(ok=False), request_id=REQ)

    def test_outer_correlation_rejected(self):
        with self.assertRaisesRegex(ValueError, "CORRELATION_MISMATCH"):
            from_receipt(receipt(request_id="another"), request_id=REQ)

    def test_model_correlation_rejected(self):
        with self.assertRaisesRegex(ValueError, "MODEL_CORRELATION_MISMATCH"):
            from_receipt(receipt({**DOC, "agentos_request_id": "another"}), request_id=REQ)

    def test_missing_required_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "REQUIRED_FIELDS_MISSING"):
            from_receipt(receipt({k: v for k, v in DOC.items() if k != "invoice_number"}), request_id=REQ)

    def test_invalid_amount_not_guessed(self):
        result = from_receipt(receipt({**DOC, "total_amount": None}), request_id=REQ)
        self.assertIsNone(result["fields"]["total_amount"])
        self.assertTrue(result["needs_review"])

    def test_sqlite_roundtrip_persists_reviewable_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InvoiceStore(Path(tmp), data_scope="test")
            image = Image.new("RGB", (24, 24), "white")
            buf = BytesIO()
            image.save(buf, format="PNG")
            ingested = store.ingest(buf.getvalue(), "fixture.png", "image/png")
            invoice_id = ingested["invoice_id"]
            with store.connect() as db:
                db.execute("UPDATE invoices SET status='needs_review' WHERE id=?", (invoice_id,))
            persisted = store.apply_verified_gpt_web_receipt(invoice_id, receipt(), request_id=REQ)
            self.assertEqual(persisted["fields"]["invoice_number"], "MY04200253")
            self.assertEqual(persisted["fields"]["seller_tax_id"], "82328968")
            self.assertEqual(persisted["fields"]["total_amount"], 50)
            self.assertEqual(persisted["status"], "needs_review")
            reread = store.get_invoice(invoice_id)
            self.assertEqual(reread["fields"]["invoice_date"], "2019-03-23")
            store.apply_verified_gpt_web_receipt(invoice_id, receipt(), request_id=REQ)
            with store.connect() as db:
                count = db.execute(
                    "SELECT COUNT(*) FROM extractions WHERE document_id=? AND engine='gpt-web-verified-receipt'",
                    (ingested["document_id"],),
                ).fetchone()[0]
            self.assertEqual(count, 1)  # retry must not duplicate evidence

            with self.assertRaisesRegex(ValueError, "NOT_REVIEWABLE"):
                self._apply_on_reviewed(store, invoice_id)

    @staticmethod
    def _apply_on_reviewed(store, invoice_id):
        with store.connect() as db:
            db.execute("UPDATE invoices SET status='accepted' WHERE id=?", (invoice_id,))
        return store.apply_verified_gpt_web_receipt(invoice_id, receipt(), request_id=REQ)

    def test_malformed_uncertainty_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNCERTAINTY_INVALID"):
            from_receipt(receipt({**DOC, "uncertain_fields": "wrong"}), request_id=REQ)


if __name__ == "__main__":
    unittest.main()
