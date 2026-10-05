import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from capabilities.stamp_recognition.runtime import (
    StampRegion, StampStore, detect_stamp_regions, fingerprint_similarity, fingerprint_stamp
)


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
