import tempfile
import unittest
from pathlib import Path

from capabilities.ocr_memory import OCRMemoryContext, OCRMemoryStore


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
