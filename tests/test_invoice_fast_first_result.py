"""Guard the opt-in invoice first-result path against synchronous Tesseract."""
import os
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from services.invoice_intake.invoice_core import extract_legacy_invoice


class InvoiceFastFirstResultTests(unittest.TestCase):
    def setUp(self):
        image = Image.new("RGB", (600, 800), "white")
        output = BytesIO()
        image.save(output, format="PNG")
        self.image_bytes = output.getvalue()
        self.template = {
            "matched": True,
            "document_type": "two_part_uniform_invoice",
            "raw_text": "",
            "fields": {"invoice_number": "AB12345678"},
            "confidence": {"invoice_number": 0.98},
        }

    def test_deferred_skips_tesseract_and_keeps_rapid_fields(self):
        with (
            patch.dict(os.environ, {"INVOICE_FAST_FALLBACK_MODE": "deferred", "INVOICE_STAMP_ASSIST_MODE": "legacy"}),
            patch("services.invoice_intake.invoice_core.extract_template_invoice", return_value=self.template),
            patch("services.invoice_intake.invoice_core.ocr_image", side_effect=AssertionError("synchronous Tesseract called")),
        ):
            result = extract_legacy_invoice(self.image_bytes)
        self.assertEqual(result.fields["invoice_number"], "AB12345678")
        self.assertIsNone(result.fields["invoice_date"])
        self.assertEqual(result.raw["fast_fallback_mode"], "deferred")
        self.assertTrue(result.raw["fallback_deferred"])
        self.assertEqual(result.raw["timings_ms"]["fallback_ocr_ms"], 0.0)
        self.assertIn(result.raw["review"]["status"], {"needs_review", "recognition_insufficient"})

    def test_legacy_keeps_synchronous_fallback_as_rollback(self):
        with (
            patch.dict(os.environ, {"INVOICE_FAST_FALLBACK_MODE": "legacy", "INVOICE_STAMP_ASSIST_MODE": "legacy"}),
            patch("services.invoice_intake.invoice_core.extract_template_invoice", return_value=self.template),
            patch("services.invoice_intake.invoice_core.ocr_image", return_value="") as ocr,
        ):
            result = extract_legacy_invoice(self.image_bytes)
        self.assertGreater(ocr.call_count, 0)
        self.assertEqual(result.fields["invoice_number"], "AB12345678")
        self.assertEqual(result.raw["fast_fallback_mode"], "legacy")
        self.assertNotIn("fallback_deferred", result.raw)


if __name__ == "__main__":
    unittest.main()
