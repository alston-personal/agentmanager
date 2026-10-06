import tempfile
import unittest
from unittest.mock import patch
from io import BytesIO
from pathlib import Path

FIXTURE_ROOT = Path('benchmarks/invoice_handwriting/fixtures')

from PIL import Image, ImageDraw

from capabilities.stamp_recognition.runtime import (
    StampRegion, StampStore, detect_stamp_regions, fingerprint_similarity, fingerprint_stamp
)
from services.invoice_intake.invoice_core import extract_legacy_invoice


def synthetic_invoice(offset=(0, 0), shade=(210, 30, 30)):
    image = Image.new("RGB", (700, 1000), "white")
    draw = ImageDraw.Draw(image)
    x, y = 430 + offset[0], 650 + offset[1]
    draw.ellipse((x, y, x + 150, y + 110), outline=shade, width=9)
    draw.rectangle((x + 35, y + 35, x + 115, y + 75), outline=shade, width=6)
    b = BytesIO()
    image.save(b, format="PNG")
    return b.getvalue()


class StampRuntimeTests(unittest.TestCase):
    def test_detects_and_crops_colored_stamp_region(self):
        regions = detect_stamp_regions(synthetic_invoice())
        self.assertTrue(regions)
        region = regions[0]
        self.assertGreater(region.confidence, 0.45)
        self.assertEqual(region.color_hint, "red")
        l, t, r, b = region.box
        self.assertLess(l, 430)
        self.assertLess(t, 650)
        self.assertGreater(r, 580)
        self.assertGreater(b, 760)

    def test_same_visual_stamp_survives_small_translation_and_ink_change(self):
        a = synthetic_invoice()
        b = synthetic_invoice(offset=(8, -6), shade=(185, 40, 40))
        fa = fingerprint_stamp(a, detect_stamp_regions(a)[0])
        fb = fingerprint_stamp(b, detect_stamp_regions(b)[0])
        self.assertGreaterEqual(fingerprint_similarity(fa, fb), 0.965)

    def test_confirmed_match_can_resolve_without_ocr(self):
        image = synthetic_invoice()
        fp = fingerprint_stamp(image, detect_stamp_regions(image)[0])
        with tempfile.TemporaryDirectory() as tmp:
            store = StampStore(Path(tmp) / "stamp.sqlite3")
            stamp_id = store.learn_confirmed(
                fp,
                entity_id="vendor-1",
                canonical_label="測試企業有限公司",
                verified_attributes={"vendor_name": "測試企業有限公司", "seller_tax_id": "16908319"},
            )
            matched = store.match(fp)
            self.assertEqual(matched.decision, "same_stamp")
            self.assertEqual(matched.stamp_id, stamp_id)
            self.assertFalse(matched.requires_confirmation)
            attrs = store.resolve_verified_attributes(stamp_id)
            self.assertEqual(attrs["seller_tax_id"], "16908319")

    def test_confirmed_same_stamp_skips_stamp_ocr(self):
        image = synthetic_invoice()
        fp = fingerprint_stamp(image, detect_stamp_regions(image)[0])
        with tempfile.TemporaryDirectory() as tmp:
            store = StampStore(Path(tmp) / "stamp.sqlite3")
            store.learn_confirmed(
                fp,
                entity_id="16908319",
                canonical_label="測試企業有限公司",
                verified_attributes={"vendor_name": "測試企業有限公司", "seller_tax_id": "16908319"},
            )
            template = {
                "matched": True,
                "document_type": "three_part_uniform_invoice",
                "raw_text": "",
                "fields": {
                    "invoice_number": "AB12345678",
                    "invoice_date": "2026-10-05",
                    "amount_before_tax": 1000,
                    "tax_amount": 50,
                    "total_amount": 1050,
                },
                "confidence": {
                    "invoice_number": 0.98,
                    "invoice_date": 0.98,
                    "amount_before_tax": 0.98,
                    "tax_amount": 0.98,
                    "total_amount": 0.98,
                },
                "visual_amounts": True,
                "total_amount": 1050,
            }
            with patch("services.invoice_intake.invoice_core.extract_template_invoice", return_value=template), \
                 patch("services.invoice_intake.invoice_core.ocr_stamp_text") as stamp_ocr:
                result = extract_legacy_invoice(image, stamp_store=store)
            stamp_ocr.assert_not_called()
            self.assertEqual(result.fields["vendor_name"], "測試企業有限公司")
            self.assertEqual(result.fields["seller_tax_id"], "16908319")
            self.assertEqual(result.raw["stamp_recognition"]["status"], "MATCHED_CONFIRMED")
            self.assertEqual(result.raw["field_sources"]["vendor_name"], "stamp_registry")

    def test_public_invoice_fixtures_detect_stamp_candidates(self):
        # Real public invoice photos catch detector assumptions that synthetic
        # red/blue drawings do not. These three fixtures visibly contain seller stamps.
        fixture_names = [
            "tw-2part-my04200253.jpg",
            "tw-3part-rp54268249.jpg",
            "tw-triplicate-wikimedia.jpg",
        ]
        detected = {}
        for name in fixture_names:
            data = (FIXTURE_ROOT / name).read_bytes()
            regions = detect_stamp_regions(data)
            detected[name] = regions
        self.assertGreaterEqual(
            sum(bool(regions) for regions in detected.values()),
            2,
            {name: [r.box for r in regions] for name, regions in detected.items()},
        )

    def test_detected_stamp_roi_is_used_for_fallback_ocr(self):
        image = synthetic_invoice()
        region = detect_stamp_regions(image)[0]
        template = {
            "matched": True,
            "document_type": "three_part_uniform_invoice",
            "raw_text": "",
            "fields": {
                "invoice_number": "AB12345678",
                "invoice_date": "2026-10-05",
                "amount_before_tax": 1000,
                "tax_amount": 50,
                "total_amount": 1050,
            },
            "confidence": {
                "invoice_number": 0.99,
                "invoice_date": 0.99,
                "amount_before_tax": 0.99,
                "tax_amount": 0.99,
                "total_amount": 0.99,
            },
            "visual_amounts": True,
            "total_amount": 1050,
        }
        seen_sizes = []

        def fake_stamp_ocr(crop, *, digits_only=False, fast=False):
            seen_sizes.append((crop.size, digits_only, fast))
            if digits_only:
                return ["16908319"]
            return ["測試企業有限公司"]

        with patch("services.invoice_intake.invoice_core.extract_template_invoice", return_value=template), \
             patch("services.invoice_intake.invoice_core.detect_stamp_regions", return_value=[region]), \
             patch("services.invoice_intake.invoice_core.ocr_stamp_text", side_effect=fake_stamp_ocr):
            result = extract_legacy_invoice(image)

        self.assertTrue(seen_sizes)
        expected_size = (region.box[2] - region.box[0], region.box[3] - region.box[1])
        self.assertEqual(seen_sizes[0][0], expected_size)
        self.assertTrue(all(fast for _, _, fast in seen_sizes))
        self.assertEqual(result.fields["seller_tax_id"], "16908319")
        self.assertEqual(result.fields["vendor_name"], "測試企業有限公司")

    def test_unknown_stamp_never_auto_resolves_from_text(self):
        a = synthetic_invoice()
        other = Image.new("RGB", (700, 1000), "white")
        draw = ImageDraw.Draw(other)
        draw.rectangle((440, 650, 590, 760), outline=(210, 30, 30), width=9)
        draw.line((450, 700, 580, 700), fill=(210, 30, 30), width=8)
        b = BytesIO(); other.save(b, format="PNG")
        other_bytes = b.getvalue()
        fa = fingerprint_stamp(a, detect_stamp_regions(a)[0])
        fb = fingerprint_stamp(other_bytes, detect_stamp_regions(other_bytes)[0])
        with tempfile.TemporaryDirectory() as tmp:
            store = StampStore(Path(tmp) / "stamp.sqlite3")
            store.learn_confirmed(fa, entity_id="vendor-1",
                                  canonical_label="同公司",
                                  verified_attributes={"vendor_name": "同公司", "seller_tax_id": "16908319"})
            matched = store.match(fb)
            self.assertNotEqual(matched.decision, "same_stamp")


if __name__ == "__main__":
    unittest.main()
