"""Fail-closed deterministic part of Mio's image-manifest gate.

Usage:
 python scripts/validate_mio_image_manifest.py --manifest FILE --world FILE --wardrobe FILE --phase pre
 python scripts/validate_mio_image_manifest.py --manifest FILE --world FILE --wardrobe FILE --phase post

For A/B outfit content trusted dispatcher MUST pass --require-outfit.\nThis validates IDs and evidence bookkeeping, NOT image pixels or ownership.
The post phase requires separately attested visual review evidence.
"""
import argparse
import json
import sys
from pathlib import Path


CHECKS = ("pre_generation", "post_generation", "rights", "caption_facts", "identity", "solo_capture")
WEARABLE_CATEGORIES = {"top", "bottom", "dress", "outerwear", "shoes", "bag", "jewelry",
                       "hair_accessories", "hat", "socks", "belt", "other_accessories"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate(manifest, world, wardrobe, phase, require_outfit=False):
    errors = []
    if manifest.get("schema") != "milkcat.image-manifest/v1":
        errors.append("wrong_manifest_schema")
    if manifest.get("publication", {}).get("published"):
        errors.append("already_published")
    if not manifest.get("asset_id") or not manifest.get("draft_id"):
        errors.append("missing_asset_or_draft_id")
    if manifest.get("character_id") != world.get("character_id") or manifest.get("character_id") != wardrobe.get("character_id"):
        errors.append("character_id_mismatch")
    world_items = {x["id"]: x for x in world.get("entries", [])}
    wardrobe_items = {x["item_id"]: x for x in wardrobe.get("items", [])}
    if len(world_items) != len(world.get("entries", [])) or len(wardrobe_items) != len(wardrobe.get("items", [])):
        errors.append("duplicate_catalog_ids")
    if manifest.get("scene_id") not in world_items or world_items.get(manifest.get("scene_id"), {}).get("kind") != "scene":
        errors.append("missing_scene")
    if manifest.get("provenance_mode") == "unknown":
        errors.append("unknown_scene_provenance")
    if manifest.get("provenance_mode") == "virtual_fictional" and world_items.get(manifest.get("scene_id"), {}).get("reality_class") != "virtual_fictional":
        errors.append("scene_reality_mismatch")
    objs = manifest.get("objects", [])
    if not isinstance(objs, list) or not objs:
        errors.append("no_objects")
        objs = []
    seen = set()
    for obj in objs:
        oid = obj.get("object_id")
        if oid in seen:
            errors.append("duplicate_object:" + str(oid))
        seen.add(oid)
        cat, kind = obj.get("catalog"), obj.get("kind")
        source = wardrobe_items.get(oid) if cat == "wardrobe" else world_items.get(oid) if cat == "world_library" else None
        if source is None:
            errors.append("unresolved_object:" + str(oid))
            continue
        if kind == "wearable":
            if source.get("category") not in WEARABLE_CATEGORIES:
                errors.append("invalid_wearable_category:" + str(oid))
            if cat != "wardrobe":
                errors.append("wearable_not_from_wardrobe:" + str(oid))
            if source.get("state") not in ("usable", "approved"):
                errors.append("wearable_not_approved:" + str(oid))
            if source.get("rights", {}).get("product_image_use") not in ("approved", "licensed", "not_required_original_design"):
                errors.append("wearable_rights_missing:" + str(oid))
        elif cat == "wardrobe":
            errors.append("nonwearable_wardrobe_object:" + str(oid))
        elif kind != source.get("kind"):
            errors.append("object_kind_mismatch:" + str(oid))
        if source.get("rights", {}).get("media_use") == "prohibited":
            errors.append("media_use_prohibited:" + str(oid))
        if phase == "post" and obj.get("visible") is True and obj.get("verification") != "matched":
            errors.append("unmatched_visible_object:" + str(oid))
        if phase == "post" and obj.get("visible") is None:
            errors.append("visibility_not_reviewed:" + str(oid))
    if manifest.get("scene_id") not in seen:
        errors.append("scene_not_in_objects")
    if require_outfit:
        worn = [wardrobe_items.get(o.get("object_id"), {}) for o in objs
                if o.get("catalog") == "wardrobe" and o.get("kind") == "wearable"
                and (phase == "pre" or o.get("visible") is True)]
        categories = {item.get("category") for item in worn}
        if not ({"top", "bottom"} <= categories or "dress" in categories):
            errors.append("outfit_missing_top_bottom_or_dress")
    extras = manifest.get("unregistered_visible_objects", [])
    if extras:
        errors.append("unregistered_visible_objects")
    checks = manifest.get("checks", {})
    needed = CHECKS if phase == "post" else ("pre_generation", "rights", "identity")
    for key in needed:
        check = checks.get(key, {})
        if check.get("status") != "pass" or not check.get("evidence"):
            errors.append("check_not_evidenced:" + key)
    if phase == "post":
        if manifest.get("state") != "verified":
            errors.append("manifest_not_verified")
        if not manifest.get("image_ref") or not manifest.get("image_sha256"):
            errors.append("missing_image_reference_or_hash")
        if not manifest.get("reviewer") or not manifest.get("reviewed_at"):
            errors.append("missing_independent_review_record")
        if not manifest.get("publication", {}).get("allowed"):
            errors.append("publication_not_allowed")
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--world", required=True)
    parser.add_argument("--wardrobe", required=True)
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    parser.add_argument("--require-outfit", action="store_true",
                        help="Set by trusted outfit-post dispatch, never derive from user-editable manifest")
    args = parser.parse_args()
    errors = validate(load(args.manifest), load(args.world), load(args.wardrobe), args.phase,
                      require_outfit=args.require_outfit)
    print(json.dumps({"phase": args.phase, "allowed": not errors, "errors": errors}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
