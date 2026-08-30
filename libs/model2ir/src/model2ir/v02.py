from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from . import core as _v01
from .reversible import embed_ir_in_gltf, recover_embedded_ir, reversible_status, ir_digest


def load_asset(path: str | Path):
    return _v01.load_asset(path)


def extract_ir(asset_or_path) -> dict[str, Any]:
    asset = asset_or_path if isinstance(asset_or_path, _v01.Asset) else _v01.load_asset(asset_or_path)
    out = _v01.extract_ir(asset)
    out["schema"] = "model2ir-character-ir/v0.2"
    status = reversible_status(asset.gltf)
    out["reversibility"] = status
    embedded = recover_embedded_ir(asset.gltf)
    if embedded is not None:
        out["canonical_ir"] = embedded
        out["canonical_ir_digest"] = ir_digest(embedded)
        out["canonical_recovery"] = {
            "mode": "lossless-embedded",
            "verified": True,
            "semantic_inference_required": False,
        }
    else:
        out["canonical_ir"] = None
        out["canonical_recovery"] = {
            "mode": "inferred-only",
            "verified": False,
            "semantic_inference_required": True,
        }
    out["provenance"]["extractor"] = "model2ir/v0.2"
    return out


def _canonical_payload(ir: dict[str, Any]) -> dict[str, Any] | None:
    c = ir.get("canonical_ir")
    if isinstance(c, dict):
        return c
    if ir.get("schema", "").startswith("character-") or "inferred" in ir or "observed" in ir:
        return ir
    return None


def deep_diff(a: Any, b: Any, path: str = "$") -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    if type(a) is not type(b):
        return [{"path": path, "kind": "type", "a": a, "b": b}]
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            p = f"{path}.{key}"
            if key not in a:
                diffs.append({"path": p, "kind": "added", "b": b[key]})
            elif key not in b:
                diffs.append({"path": p, "kind": "lost", "a": a[key]})
            else:
                diffs.extend(deep_diff(a[key], b[key], p))
        return diffs
    if isinstance(a, list):
        if len(a) != len(b):
            diffs.append({"path": path, "kind": "length", "a": len(a), "b": len(b)})
        for i, (x, y) in enumerate(zip(a, b)):
            diffs.extend(deep_diff(x, y, f"{path}[{i}]"))
        return diffs
    if a != b:
        diffs.append({"path": path, "kind": "changed", "a": a, "b": b})
    return diffs


def diff_ir(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    base = _v01.diff_ir(a, b)
    ca, cb = _canonical_payload(a), _canonical_payload(b)
    canonical = None
    if ca is not None and cb is not None:
        differences = deep_diff(ca, cb)
        canonical = {
            "available": True,
            "exact": not differences,
            "difference_count": len(differences),
            "differences": differences,
            "a_digest": ir_digest(ca),
            "b_digest": ir_digest(cb),
        }
    else:
        canonical = {"available": False, "exact": False, "difference_count": None, "differences": []}
    return {
        "schema": "model2ir-diff/v0.2",
        "semantic": base["semantic"],
        "geometry_numeric": base["geometry_numeric"],
        "canonical": canonical,
    }


def score_roundtrip(source_ir: dict[str, Any], recovered_ir: dict[str, Any]) -> dict[str, Any]:
    d = diff_ir(source_ir, recovered_ir)
    canonical = d["canonical"]
    exact = bool(canonical.get("available") and canonical.get("exact"))
    return {
        "schema": "model2ir-roundtrip-score/v0.2",
        "lossless_reversible": exact,
        "canonical_exact": exact,
        "canonical_difference_count": canonical.get("difference_count"),
        "semantic_preservation": d["semantic"]["jaccard"],
        "diff": d,
    }


def reconcile_ir(image_ir: dict[str, Any], model_ir: dict[str, Any]) -> dict[str, Any]:
    out = _v01.reconcile_ir(image_ir, model_ir)
    out["schema"] = "model2ir-reconciliation/v0.2"
    out["model_reversibility"] = model_ir.get("reversibility", {"mode": "unknown", "lossless": False})
    if model_ir.get("canonical_ir") is not None:
        out["embedded_canonical_ir_digest"] = model_ir.get("canonical_ir_digest")
        out["policy"] = "embedded canonical IR may be recovered exactly; inferred 3D semantics remain candidate evidence"
    return out


def compile_reversible_gltf(base_gltf: dict[str, Any], canonical_ir: dict[str, Any]) -> dict[str, Any]:
    return embed_ir_in_gltf(base_gltf, canonical_ir)


def save_reversible_gltf(base_gltf: dict[str, Any], canonical_ir: dict[str, Any], output: str | Path) -> Path:
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(compile_reversible_gltf(base_gltf, canonical_ir), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p
