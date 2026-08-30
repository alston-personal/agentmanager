#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from model2ir import audit_asset, extract_ir, stabilize_external_ir, ir_digest

VIEWS = ("front", "yaw45", "right", "back")


def dump(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--renderer", default="scripts/character_blueprint_glb_render.mjs")
    args = ap.parse_args()

    asset = Path(args.asset).resolve()
    out = Path(args.out).resolve()
    case_dir = out / args.case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_asset(asset)
    raw_ir = extract_ir(asset)
    stable_ir = stabilize_external_ir(raw_ir)
    stable_digest = ir_digest(stable_ir)

    # Training data may contain ambiguity, but never silently invent truth.
    stability = audit.get("stability", "unstable")
    if stability == "unstable":
        raise SystemExit("asset audit is unstable; refusing teacher dataset admission")

    local_asset = case_dir / "model.glb"
    if asset.suffix.lower() != ".glb":
        raise SystemExit("teacher renderer v0.7 currently requires GLB input")
    shutil.copy2(asset, local_asset)

    result_stub = case_dir / "render-result.json"
    dump(result_stub, {"case_id": args.case_id, "source_sha256": sha256(asset)})
    subprocess.run([
        "node", args.renderer,
        "--glb", str(local_asset),
        "--out", str(case_dir),
        "--result", str(result_stub),
    ], check=True)

    render_result = json.loads(result_stub.read_text(encoding="utf-8"))
    renders = render_result["renders"]
    missing = [v for v in VIEWS if v not in renders or not (case_dir / renders[v]).exists()]
    if missing:
        raise SystemExit(f"missing canonical renders: {missing}")

    dump(case_dir / "character-ir.json", stable_ir)
    dump(case_dir / "audit.json", audit)

    examples = []
    for view in VIEWS:
        image = case_dir / renders[view]
        examples.append({
            "example_id": f"{args.case_id}:{view}",
            "view": view,
            "image": str(Path(args.case_id) / image.name),
            "image_sha256": sha256(image),
            "target_ir": str(Path(args.case_id) / "character-ir.json"),
            "target_ir_digest": stable_digest,
            "truth_status": stable_ir.get("truth_status", "candidate"),
            "semantic_authority": audit.get("semantic_authority"),
            "unresolved": audit.get("unresolved", []),
        })

    manifest = {
        "schema": "model2ir-teacher-dataset/v0.7",
        "policy": {
            "label_kind": "stabilized-evidence-preserving-character-ir",
            "unknowns_are_labels_not_errors": True,
            "external_first_import_claimed_lossless": False,
            "canonical_views": list(VIEWS),
        },
        "cases": [{
            "case_id": args.case_id,
            "source_asset": str(Path(args.case_id) / "model.glb"),
            "source_sha256": sha256(asset),
            "audit": str(Path(args.case_id) / "audit.json"),
            "target_ir": str(Path(args.case_id) / "character-ir.json"),
            "target_ir_digest": stable_digest,
            "stability": stability,
        }],
        "examples": examples,
    }
    dump(out / "manifest.json", manifest)
    print(json.dumps({
        "ok": True,
        "case_id": args.case_id,
        "stability": stability,
        "examples": len(examples),
        "target_ir_digest": stable_digest,
    }))


if __name__ == "__main__":
    main()
