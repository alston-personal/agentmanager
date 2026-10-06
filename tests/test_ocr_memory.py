import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from capabilities.ocr_memory import OCRMemoryContext, OCRMemoryStore
from services.invoice_intake.invoice_core import InvoiceStore, extract_legacy_invoice


class OCRMemoryTests(unittest.TestCase):
    def test_same_stamp_exact_error_can_auto_correct_after_one_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OCRMemoryStore(Path(tmp) / "memory.sqlite3")
            ctx = OCRMemoryContext(template_id="three_part", stamp_id="stamp-1", entity_id="vendor-1")
            store.remember(
                field_name="total_amount",
                observed_value="1O5O",
                corrected_value=1050,
                context=ctx,
                actor="tester",
            )
            decision = store.resolve(
                field_name="total_amount",
                observed_value="1O5O",
                context=ctx,
            )
            self.assertEqual(decision.decision, "auto_correct")
            self.assertEqual(decision.corrected_value, 1050)
            self.assertGreaterEqual(decision.score, 0.99)

    def test_same_entity_template_needs_repeated_confirmation_before_auto(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OCRMemoryStore(Path(tmp) / "memory.sqlite3")
            learned = OCRMemoryContext(template_id="three_part", entity_id="vendor-1")
            current = OCRMemoryContext(template_id="three_part", entity_id="vendor-1")
            store.remember(
                field_name="vendor_name",
                observed_value="好日子食晶有限公司",
                corrected_value="好日子食品有限公司",
                context=learned,
            )
            first = store.resolve(
                field_name="vendor_name",
                observed_value="好日子食晶有限公司",
                context=current,
            )
            self.assertEqual(first.decision, "suggest")

            store.remember(
                field_name="vendor_name",
                observed_value="好日子食晶有限公司",
                corrected_value="好日子食品有限公司",
                context=learned,
            )
            second = store.resolve(
                field_name="vendor_name",
                observed_value="好日子食晶有限公司",
                context=current,
            )
            self.assertEqual(second.decision, "auto_correct")
            self.assertEqual(second.confirmed_count, 2)

    def test_template_only_never_auto_corrects(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OCRMemoryStore(Path(tmp) / "memory.sqlite3")
            learned = OCRMemoryContext(template_id="three_part")
            for _ in range(4):
                store.remember(
                    field_name="invoice_date",
                    observed_value="2026-10-0S",
                    corrected_value="2026-10-05",
                    context=learned,
                )
            decision = store.resolve(
                field_name="invoice_date",
                observed_value="2026-10-0S",
                context=OCRMemoryContext(template_id="three_part"),
            )
            self.assertEqual(decision.decision, "suggest")
            self.assertLess(decision.score, 0.90)

    def test_review_persists_human_correction_with_extraction_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = InvoiceStore(root, data_scope="test")
            image = Image.new("RGB", (64, 64), "white")
            buf = BytesIO()
            image.save(buf, format="JPEG")
            created = store.ingest(
                buf.getvalue(),
                "correction.jpg",
                "image/jpeg",
                source_type="upload",
                batch_id="batch-correction",
            )
            with store.connect() as db:
                db.execute(
                    """UPDATE invoices SET
                         invoice_number='AB12345678', invoice_date='2026-10-05',
                         vendor_name='好日子食晶有限公司', seller_tax_id='16908319',
                         amount_before_tax=1000, tax_amount=50, total_amount=1050,
                         status='quick_confirm'
                       WHERE id=?""",
                    (created["invoice_id"],),
                )
                raw = {
                    "engine": "test",
                    "template": {"document_type": "three_part_uniform_invoice"},
                    "stamp_recognition": {
                        "status": "MATCHED_CONFIRMED",
                        "stamp_id": "stamp-1",
                        "entity_id": "16908319",
                    },
                }
                db.execute(
                    "INSERT INTO extractions VALUES(?,?,?,?,?)",
                    (
                        "ex-correction",
                        created["document_id"],
                        "test",
                        __import__("json").dumps(raw, ensure_ascii=False),
                        "2026-10-05T00:00:00Z",
                    ),
                )

            store.review(
                created["invoice_id"],
                "tester",
                {
                    "invoice_number": "AB12345678",
                    "invoice_date": "2026-10-05",
                    "vendor_name": "好日子食品有限公司",
                    "seller_tax_id": "16908319",
                    "amount_before_tax": 1000,
                    "tax_amount": 50,
                    "total_amount": 1050,
                },
            )
            decision = store.ocr_memory.resolve(
                field_name="vendor_name",
                observed_value="好日子食晶有限公司",
                context=OCRMemoryContext(
                    template_id="three_part_uniform_invoice",
                    stamp_id="stamp-1",
                    entity_id="16908319",
                ),
            )
            self.assertEqual(decision.decision, "auto_correct")
            self.assertEqual(decision.corrected_value, "好日子食品有限公司")

    def test_extraction_reuses_repeated_entity_template_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = OCRMemoryStore(Path(tmp) / "memory.sqlite3")
            ctx = OCRMemoryContext(
                template_id="three_part_uniform_invoice",
                entity_id="16908319",
            )
            for _ in range(2):
                memory.remember(
                    field_name="vendor_name",
                    observed_value="好日子食晶有限公司",
                    corrected_value="好日子食品有限公司",
                    context=ctx,
                )
            template = {
                "matched": True,
                "document_type": "three_part_uniform_invoice",
                "raw_text": "",
                "fields": {
                    "invoice_number": "AB12345678",
                    "invoice_date": "2026-10-05",
                    "vendor_name": "好日子食晶有限公司",
                    "seller_tax_id": "16908319",
                    "amount_before_tax": 1000,
                    "tax_amount": 50,
                    "total_amount": 1050,
                },
                "confidence": {
                    "invoice_number": 0.99,
                    "invoice_date": 0.99,
                    "vendor_name": 0.78,
                    "seller_tax_id": 0.99,
                    "amount_before_tax": 0.99,
                    "tax_amount": 0.99,
                    "total_amount": 0.99,
                },
                "visual_amounts": True,
                "total_amount": 1050,
            }
            image = Image.new("RGB", (700, 1000), "white")
            buf = BytesIO()
            image.save(buf, format="JPEG")
            with patch(
                "services.invoice_intake.invoice_core.extract_template_invoice",
                return_value=template,
            ), patch(
                "services.invoice_intake.invoice_core.detect_stamp_regions",
                return_value=[],
            ):
                result = extract_legacy_invoice(buf.getvalue(), ocr_memory=memory)
            self.assertEqual(result.fields["vendor_name"], "好日子食品有限公司")
            self.assertEqual(result.raw["field_sources"]["vendor_name"], "ocr_memory")
            self.assertEqual(result.raw["ocr_memory"]["applied"][0]["field"], "vendor_name")
            self.assertEqual(result.review_required, False)

    def test_no_context_does_not_create_global_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = OCRMemoryStore(Path(tmp) / "memory.sqlite3")
            store.remember(
                field_name="invoice_number",
                observed_value="AB1234567B",
                corrected_value="AB12345678",
                context=OCRMemoryContext(template_id="three_part", stamp_id="stamp-1"),
            )
            decision = store.resolve(
                field_name="invoice_number",
                observed_value="AB1234567B",
                context=OCRMemoryContext(),
            )
            self.assertEqual(decision.decision, "none")


if __name__ == "__main__":
    unittest.main()
