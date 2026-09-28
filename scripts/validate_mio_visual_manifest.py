#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path

REQUIRED_FEATURES=("face_shape","eye_shape","brows","hair_flow","right_eye_beauty_mark","upper_right_canine")

def load(path):
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def fail(reason,extra=None):
    out={"ok":False,"status":"BLOCKED","reason":reason}
    if extra: out.update(extra)
    print(json.dumps(out,ensure_ascii=False))
    return 2

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--visual-anchor",required=True)
    ap.add_argument("--photo-like-face",action="store_true")
    args=ap.parse_args()

    manifest=load(args.manifest)
    anchor=load(args.visual_anchor)

    if manifest.get("schema")!="milkcat.image-manifest/v2":
        return fail("manifest_schema_not_v2")
    bp=manifest.get("identity_blueprint")
    if not isinstance(bp,dict):
        return fail("identity_blueprint_missing")
    if str(bp.get("blueprint_version"))!="2.1":
        return fail("blueprint_version_mismatch",{"actual":bp.get("blueprint_version")})
    face_bp=anchor.get("face_blueprint") if isinstance(anchor,dict) else None
    if not isinstance(face_bp,dict) or face_bp.get("schema")!="agentos.persona-face-blueprint/v2.1":
        return fail("canonical_face_blueprint_missing_or_wrong_version")
    if args.photo_like_face and bp.get("reference_pack_status")!="approved":
        return fail("approved_reference_pack_required")

    mirror=bp.get("camera_mirror_state")
    if mirror=="unknown":
        return fail("camera_mirror_state_unresolved")
    if mirror not in ("mirrored","not_mirrored"):
        return fail("camera_mirror_state_invalid",{"actual":mirror})

    features=bp.get("features")
    if not isinstance(features,dict):
        return fail("identity_features_missing")
    problems=[]
    for name in REQUIRED_FEATURES:
        item=features.get(name)
        if not isinstance(item,dict):
            problems.append({"feature":name,"reason":"missing"})
            continue
        status=item.get("status")
        evidence=item.get("evidence")
        if status=="fail":
            problems.append({"feature":name,"reason":"failed"})
        elif status=="pending":
            problems.append({"feature":name,"reason":"pending"})
        elif status=="not_visible":
            if name!="upper_right_canine":
                problems.append({"feature":name,"reason":"not_visible_not_allowed"})
            elif not isinstance(evidence,list) or not evidence:
                problems.append({"feature":name,"reason":"not_visible_requires_evidence"})
        elif status=="pass":
            if not isinstance(evidence,list) or not evidence:
                problems.append({"feature":name,"reason":"pass_requires_evidence"})
        else:
            problems.append({"feature":name,"reason":"invalid_status","status":status})
    if problems:
        return fail("identity_feature_gate_failed",{"problems":problems})

    checks=manifest.get("checks") or {}
    identity=checks.get("identity") or {}
    if identity.get("status")!="pass" or not identity.get("evidence"):
        return fail("manifest_identity_check_not_passed")

    publication=manifest.get("publication") or {}
    if publication.get("allowed") is not True:
        return fail("publication_not_allowed")

    print(json.dumps({
      "ok":True,
      "status":"PASS",
      "schema":"agentos.mio-visual-manifest-guard/v1",
      "blueprint_version":"2.1",
      "mirror_state":mirror,
      "photo_like_face":bool(args.photo_like_face),
      "reference_pack_status":bp.get("reference_pack_status"),
      "verified_features":list(REQUIRED_FEATURES)
    },ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
