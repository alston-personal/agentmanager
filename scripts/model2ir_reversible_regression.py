#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from model2ir import compile_reversible_gltf, extract_ir, ir_digest, score_roundtrip


def base_gltf(name: str = "CharacterBody") -> dict:
    return {
        "asset": {"version": "2.0", "generator": "model2ir-regression"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": name, "mesh": 0}],
        "meshes": [{"name": name, "primitives": []}],
    }


def family() -> list[dict]:
    common = {
        "schema": "character-ir/v0.6",
        "identity": {"archetype": "humanoid", "locked": True},
        "body": {"plan": "humanoid", "proportions": {"heads_tall": 7.2}},
    }
    return [
        {**common, "id": "long-hair-dress", "hair": {"length": "waist", "style": "straight"}, "garment": {"upper": "dress", "outer": None}, "accessories": []},
        {**common, "id": "short-hair-dress", "hair": {"length": "chin", "style": "bob"}, "garment": {"upper": "dress", "outer": None}, "accessories": []},
        {**common, "id": "long-hair-coat", "hair": {"length": "waist", "style": "straight"}, "garment": {"upper": "shirt", "outer": "coat"}, "accessories": []},
        {**common, "id": "mage-book", "hair": {"length": "shoulder", "style": "wavy"}, "garment": {"upper": "robe", "outer": None}, "accessories": [{"kind": "book", "relation": "held_by:right_hand"}]},
        {**common, "id": "mage-ring", "hair": {"length": "shoulder", "style": "wavy"}, "garment": {"upper": "robe", "outer": None}, "accessories": [{"kind": "magic_ring", "relation": "surrounds:torso", "class": "effect"}]},
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cases = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for i, source_ir in enumerate(family()):
            carrier = compile_reversible_gltf(base_gltf(), source_ir)
            p = root / f"case-{i}.gltf"
            p.write_text(json.dumps(carrier, ensure_ascii=False, indent=2), encoding="utf-8")
            recovered = extract_ir(p)
            score = score_roundtrip(source_ir, recovered)
            assert recovered["reversibility"]["lossless"] is True
            assert recovered["canonical_ir"] == source_ir
            assert recovered["canonical_ir_digest"] == ir_digest(source_ir)
            assert score["lossless_reversible"] is True
            assert score["canonical_difference_count"] == 0
            cases.append({
                "id": source_ir["id"],
                "digest": ir_digest(source_ir),
                "score": score,
            })

        # Arbitrary external 3D must never be reported as lossless just because it parses.
        raw = root / "external.gltf"
        raw.write_text(json.dumps(base_gltf("UnknownCharacter")), encoding="utf-8")
        external = extract_ir(raw)
        assert external["reversibility"]["lossless"] is False
        assert external["canonical_ir"] is None

        # Tampering with embedded IR while retaining old digest must be detected.
        bad = compile_reversible_gltf(base_gltf(), family()[0])
        bad["extras"]["OPENAI_model2ir_character_ir"]["character_ir"]["hair"]["length"] = "tampered"
        badp = root / "tampered.gltf"
        badp.write_text(json.dumps(bad), encoding="utf-8")
        tamper_detected = False
        try:
            extract_ir(badp)
        except ValueError as exc:
            tamper_detected = "digest mismatch" in str(exc)
        assert tamper_detected

    report = {
        "schema": "model2ir-reversible-regression/v0.2",
        "case_count": len(cases),
        "all_lossless": all(c["score"]["lossless_reversible"] for c in cases),
        "external_asset_correctly_nonlossless": True,
        "tamper_detection": True,
        "cases": cases,
        "gate": {
            "canonical_exact_required": 1.0,
            "observed": 1.0,
            "status": "PASS",
        },
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "cases": len(cases), "lossless": True, "tamper_detection": True}))


if __name__ == "__main__":
    main()
