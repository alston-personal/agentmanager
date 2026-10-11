#!/usr/bin/env python3
"""Resolve reviewed Mio images; never treat generator output as review evidence."""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

MAX_IMAGE_BYTES = 8 * 1024 * 1024
PUBLIC_BASE = "https://studio.milkcat.org/personas/mio/media/"
REVIEW_GATES = ("scene_provenance", "wardrobe_rights", "season_match", "caption_fact_check",
                "final_image_caption", "world_library", "content_assembly")


def subject_mode(media):
    mode = media.get("subject_mode", "mio_portrait")
    if mode not in ("mio_portrait", "scene_only"):
        raise ValueError("MEDIA_SUBJECT_MODE_INVALID")
    return mode


def authorize_subject(root, media):
    mode = subject_mode(media)
    if mode == "scene_only":
        policy = load(within(root, "visual_content_policy.json"))
        if not isinstance(policy,dict):
            raise ValueError("MEDIA_SCENE_POLICY_NOT_ENABLED")
        scene_policy=policy.get("scene_only_images")
        if not isinstance(scene_policy,dict) or scene_policy.get("enabled") is not True:
            raise ValueError("MEDIA_SCENE_POLICY_NOT_ENABLED")
        if media.get("wardrobe_ids") != []:
            raise ValueError("MEDIA_SCENE_WARDROBE_NOT_ALLOWED")
    return mode


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def within(root, ref):
    if not isinstance(ref, str) or not ref or Path(ref).is_absolute():
        raise ValueError("MEDIA_REFERENCE_INVALID")
    path = (Path(root) / ref).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("MEDIA_REFERENCE_INVALID")
    return path


def caption_digest(action):
    return digest(str(action.get("primary_text") or "").strip().encode())


def selection_digest(action):
    media=action.get("media_intent") or {}
    keys=["mode","prompt","source_ref"]
    keys += [k for k in ("world_ids","wardrobe_ids","subject_mode") if k in media]
    return digest(json.dumps({k:media.get(k) for k in keys},
                            sort_keys=True,ensure_ascii=False).encode())


def eligible_world(item):
    return item.get("lifecycle")=="usable" and (item.get("source") or {}).get("rights") in (
        "original_description_only","owner_authorized","licensed","public_domain")


def eligible_wardrobe(item):
    rights=item.get("rights") or {}
    return item.get("state") not in (None,"candidate","archived") and rights.get("product_image_use") in (
        "approved","licensed","owner_authorized") and bool(rights.get("evidence_ref"))


def validate_sources(root, provenance):
    world_ids=provenance.get("world_ids")
    wardrobe_ids=provenance.get("wardrobe_ids")
    if not isinstance(world_ids,list) or not world_ids or not isinstance(wardrobe_ids,list):
        raise ValueError("MEDIA_ASSEMBLY_IDS_REQUIRED")
    for ids in (world_ids,wardrobe_ids):
        if len(ids)>24 or any(not isinstance(key,str) or not key or len(key)>200 for key in ids) or len(set(ids))!=len(ids):
            raise ValueError("MEDIA_ASSEMBLY_IDS_REQUIRED")
    world=load(within(root,"world_library/catalog.json"))
    wardrobe=load(within(root,"wardrobe/catalog.json"))
    by_world={x.get("id"):x for x in world.get("entries",[])}
    by_wardrobe={x.get("item_id"):x for x in wardrobe.get("items",[])}
    for key in world_ids:
        if not eligible_world(by_world.get(key) or {}):
            raise ValueError("MEDIA_WORLD_SOURCE_NOT_USABLE")
    for key in wardrobe_ids:
        if not eligible_wardrobe(by_wardrobe.get(key) or {}):
            raise ValueError("MEDIA_WARDROBE_RIGHTS_UNVERIFIED")
    return [by_world[k] for k in world_ids], [by_wardrobe[k] for k in wardrobe_ids]


def read_public_image(url, expected):
    if url != PUBLIC_BASE + expected + ".jpg" and url != PUBLIC_BASE + expected + ".png":
        raise ValueError("MEDIA_URL_INVALID")
    with urllib.request.urlopen(url, timeout=20) as response:
        data = response.read(MAX_IMAGE_BYTES + 1)
        if response.geturl() != url or response.status != 200:
            raise ValueError("MEDIA_PUBLIC_READ_FAILED")
        expected_type="image/png" if url.endswith(".png") else "image/jpeg"
        if str(response.headers.get("Content-Type", "")).lower().split(";")[0].strip()!=expected_type:
            raise ValueError("MEDIA_PUBLIC_TYPE_INVALID")
    if len(data) > MAX_IMAGE_BYTES or digest(data) != expected:
        raise ValueError("MEDIA_PUBLIC_DIGEST_MISMATCH")
    return data


def review_manifest(root, action, manifest):
    """Bind a real review to this action, caption, bytes and current policies."""
    if manifest.get("action_id") != action.get("action_id") or manifest.get("caption_sha256") != caption_digest(action) or manifest.get("media_selection_sha256")!=selection_digest(action):
        raise ValueError("MEDIA_REVIEW_INTENT_MISMATCH")
    sha = manifest.get("image_sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("MEDIA_DIGEST_INVALID")
    policy = within(root, "visual_content_policy.json")
    anchor = within(root, "visual_anchor_spec.json")
    references = within(root, "reference_pack.json")
    for field, path in (("visual_policy_sha256", policy), ("visual_anchor_sha256", anchor),
                        ("reference_pack_sha256", references)):
        if manifest.get(field) != digest(path.read_bytes()):
            raise ValueError("MEDIA_REVIEW_POLICY_STALE")
    if "world_policy_sha256" in manifest and manifest["world_policy_sha256"]!=digest(within(root,"world_library/policy.json").read_bytes()):
        raise ValueError("MEDIA_REVIEW_POLICY_STALE")
    pack = load(references)
    if pack.get("status") != "approved":
        raise ValueError("MEDIA_REFERENCE_PACK_NOT_APPROVED")
    reference_sha = (pack.get("canonical_asset") or {}).get("sha256")
    if (pack.get("canonical_asset") or {}).get("reference_id") not in (pack.get("approved_reference_ids") or []):
        raise ValueError("MEDIA_CANONICAL_REFERENCE_NOT_APPROVED")
    if manifest.get("reference_image_sha256") != reference_sha or not reference_sha:
        raise ValueError("MEDIA_CANONICAL_REFERENCE_MISMATCH")
    checks = manifest.get("checks") or {}
    for gate in REVIEW_GATES:
        check = checks.get(gate) or {}
        if check.get("status") != "pass" or not isinstance(check.get("evidence"), list) or not check["evidence"]:
            raise ValueError("MEDIA_CONTENT_REVIEW_REQUIRED")
    provenance = manifest.get("provenance") or {}
    if not provenance.get("source_ref") or not provenance.get("rights_evidence_ref"):
        raise ValueError("MEDIA_PROVENANCE_REQUIRED")
    media=action.get("media_intent") or {}
    mode = authorize_subject(root, media)
    if subject_mode(manifest) != mode:
        raise ValueError("MEDIA_REVIEW_INTENT_MISMATCH")
    if mode == "scene_only":
        if provenance.get("wardrobe_ids") != []:
            raise ValueError("MEDIA_SCENE_WARDROBE_NOT_ALLOWED")
        validate_scene_review(manifest)
    if media.get("mode")=="existing_verified" and provenance.get("source_ref")!=media.get("source_ref"):
        raise ValueError("MEDIA_REVIEW_INTENT_MISMATCH")
    if provenance.get("commercial_state") != "organic_no_brand":
        raise ValueError("MEDIA_COMMERCIAL_REVIEW_REQUIRED")
    # Content selection remains data-owned. Do not upgrade catalog candidates
    # or unverified retail rights because a model wrote "pass" in a manifest.
    validate_sources(root,provenance)
    for field, path in (("world_catalog_sha256", within(root, "world_library/catalog.json")),
                        ("wardrobe_catalog_sha256", within(root, "wardrobe/catalog.json"))):
        if manifest.get(field) != digest(path.read_bytes()):
            raise ValueError("MEDIA_REVIEW_POLICY_STALE")
    alt = manifest.get("image_alt_text")
    if not isinstance(alt, str) or not 1 <= len(alt.strip()) <= 1000:
        raise ValueError("MEDIA_ALT_TEXT_REQUIRED")
    return sha, alt.strip()


def validate_scene_review(manifest):
    """Scene evidence must establish absence of people, not a hidden Mio face."""
    scene = manifest.get("scene_only_review")
    if not isinstance(scene, dict) or scene.get("image_seen") is not True:
        raise ValueError("MEDIA_SCENE_REVIEW_REQUIRED")
    for field in ("people_visible", "face_visible", "unlisted_wearables"):
        if scene.get(field) is not False:
            raise ValueError("MEDIA_SCENE_PERSON_OR_WEARABLE_PRESENT")
    if scene.get("visible_wardrobe_ids") != [] or manifest.get("identity_blueprint") is not None:
        raise ValueError("MEDIA_SCENE_REVIEW_REQUIRED")
    for name in ("no_people", "visual_quality"):
        check = (manifest.get("checks") or {}).get(name)
        if not isinstance(check, dict) or check.get("status") != "pass":
            raise ValueError("MEDIA_SCENE_REVIEW_REQUIRED")
        evidence = check.get("evidence")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 8 or any(
            not isinstance(x, str) or not x.strip() or len(x) > 800 for x in evidence
        ):
            raise ValueError("MEDIA_SCENE_REVIEW_REQUIRED")


def validate_review(root, action, manifest_path):
    manifest = load(manifest_path)
    sha, alt = review_manifest(root, action, manifest)
    validator = Path(__file__).with_name("validate_mio_visual_manifest.py")
    flag = "--scene-only" if subject_mode(action.get("media_intent") or {}) == "scene_only" else "--photo-like-face"
    result = subprocess.run([sys.executable, str(validator), "--manifest", str(manifest_path),
                             "--visual-anchor", str(within(root, "visual_anchor_spec.json")),
                             flag], capture_output=True, text=True, timeout=15)
    if result.returncode != 0 or json.loads(result.stdout or "{} ").get("ok") is not True:
        raise ValueError("MEDIA_SCENE_REVIEW_REQUIRED" if flag=="--scene-only" else "MEDIA_IDENTITY_REVIEW_REQUIRED")
    return manifest, sha, alt


def prepare_asset(root, action, manifest_path, output_dir):
    manifest, sha, alt = validate_review(root, action, manifest_path)
    source = Path(manifest.get("image_path") or "")
    draft_root = Path(os.environ.get("AGENTOS_MIO_MEDIA_OUTPUT_DIR") or "/home/ubuntu/agent-data/media/mio/generated").resolve()
    if not source.is_file() or not source.resolve().is_relative_to(draft_root):
        raise ValueError("MEDIA_DRAFT_PATH_INVALID")
    data = source.read_bytes()
    if not 32 <= len(data) <= MAX_IMAGE_BYTES or digest(data) != sha:
        raise ValueError("MEDIA_DRAFT_DIGEST_MISMATCH")
    suffix = ".jpg" if data.startswith(b"\xff\xd8\xff") else ".png" if data.startswith(b"\x89PNG\r\n\x1a\n") else None
    if not suffix:
        raise ValueError("MEDIA_IMAGE_FORMAT_UNSUPPORTED")
    destination = Path(output_dir) / (sha + suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and digest(destination.read_bytes()) != sha:
        raise ValueError("MEDIA_HOSTED_ASSET_CONFLICT")
    if not destination.exists():
        temporary = destination.with_suffix(suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.chmod(0o644)
        os.replace(temporary, destination)
    url = PUBLIC_BASE + destination.name
    read_public_image(url, sha)
    return {"schema": "agentos.persona-reviewed-media/v1", "status": "VALIDATED",
            "action_id": action["action_id"], "caption_sha256": caption_digest(action),
            "media_selection_sha256":selection_digest(action),
            "image_sha256": sha, "image_url": url, "image_alt_text": alt,
            "manifest_ref": str(Path(manifest_path).relative_to(root)),
            "manifest_sha256": digest(Path(manifest_path).read_bytes()),
            "asset_verified": True, "uploaded": True, "publication_allowed": True}


def resolve_asset(root, action):
    media = action.get("media_intent") or {}
    if media.get("status") != "validated":
        raise ValueError("MEDIA_NOT_VALIDATED")
    receipt_path = within(root, media.get("asset_receipt_ref"))
    receipt = load(receipt_path)
    if receipt.get("schema") != "agentos.persona-reviewed-media/v1" or receipt.get("status") != "VALIDATED" or receipt.get("asset_verified") is not True or receipt.get("uploaded") is not True or receipt.get("publication_allowed") is not True:
        raise ValueError("MEDIA_ASSET_RECEIPT_INVALID")
    manifest_path = within(root, receipt.get("manifest_ref"))
    if digest(manifest_path.read_bytes()) != receipt.get("manifest_sha256"):
        raise ValueError("MEDIA_REVIEW_CHANGED")
    _, sha, alt = validate_review(root, action, manifest_path)
    if receipt.get("action_id") != action.get("action_id") or receipt.get("caption_sha256") != caption_digest(action) or receipt.get("media_selection_sha256")!=selection_digest(action) or receipt.get("image_sha256") != sha or receipt.get("image_alt_text") != alt:
        raise ValueError("MEDIA_ASSET_INTENT_MISMATCH")
    read_public_image(receipt.get("image_url"), sha)
    return receipt
