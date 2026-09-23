import copy
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_mio_image_manifest.py"
spec = importlib.util.spec_from_file_location("mio_manifest_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ManifestGateTest(unittest.TestCase):
    def setUp(self):
        self.world = {"character_id": "mio-001", "entries": [
            {"id": "scene-1", "kind": "scene", "reality_class": "virtual_fictional"},
            {"id": "food-1", "kind": "food", "reality_class": "virtual_fictional"}]}
        self.wardrobe = {"character_id": "mio-001", "items": [
            {"item_id": "shirt-1", "state": "approved",
             "rights": {"product_image_use": "approved"}}]}
        self.m = {"schema": "milkcat.image-manifest/v1", "asset_id": "a1", "draft_id": "d1",
                  "character_id": "mio-001", "state": "planned",
                  "provenance_mode": "virtual_fictional", "scene_id": "scene-1",
                  "objects": [
                      {"object_id": "scene-1", "catalog": "world_library", "kind": "scene",
                       "visible": None, "verification": "pending"},
                      {"object_id": "shirt-1", "catalog": "wardrobe", "kind": "wearable",
                       "visible": None, "verification": "pending"}],
                  "unregistered_visible_objects": [],
                  "checks": {k: {"status": "pass", "evidence": ["review-receipt"]}
                             for k in gate.CHECKS},
                  "publication": {"allowed": False, "published": False},
                  "image_ref": None, "image_sha256": None}

    def check(self, phase="pre"):
        return gate.validate(self.m, self.world, self.wardrobe, phase)

    def test_pre_allows_only_grounded_selection(self):
        self.assertEqual([], self.check())

    def test_unknown_item_is_blocked(self):
        self.m["objects"][1]["object_id"] = "invented-necklace"
        self.assertIn("unresolved_object:invented-necklace", self.check())

    def test_candidate_without_rights_is_blocked(self):
        self.wardrobe["items"][0]["state"] = "candidate"
        self.wardrobe["items"][0]["rights"]["product_image_use"] = "unverified"
        self.assertIn("wearable_not_approved:shirt-1", self.check())
        self.assertIn("wearable_rights_missing:shirt-1", self.check())

    def test_extra_visible_item_is_blocked(self):
        self.m["unregistered_visible_objects"] = [{"description": "bracelet"}]
        self.assertIn("unregistered_visible_objects", self.check())

    def test_post_requires_visual_evidence_not_just_manifest_claim(self):
        self.m["state"] = "verified"
        self.m["publication"]["allowed"] = True
        self.m["image_ref"] = "image.png"
        self.m["image_sha256"] = "0" * 64
        for obj in self.m["objects"]:
            obj["visible"] = True
            obj["verification"] = "matched"
        self.assertIn("missing_independent_review_record", self.check("post"))
        self.m["reviewer"], self.m["reviewed_at"] = "visual-review-1", "2026-09-23T10:00:00+08:00"
        self.assertEqual([], self.check("post"))

    def test_published_manifest_cannot_be_reused(self):
        self.m["publication"]["published"] = True
        self.assertIn("already_published", self.check())


if __name__ == "__main__":
    unittest.main()
