from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JSON_CHUNK = 0x4E4F534A
SUPPORTED = {".glb", ".gltf", ".vrm"}


@dataclass(frozen=True)
class Asset:
    path: Path
    kind: str
    gltf: dict[str, Any]
    bytes_size: int
    chunks: list[dict[str, int]]


def _read_glb(path: Path) -> tuple[dict[str, Any], list[dict[str, int]]]:
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError("GLB too small")
    magic, version, total = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("not a GLB/VRM container")
    if version != 2:
        raise ValueError(f"unsupported GLB version {version}")
    if total > len(data):
        raise ValueError("declared GLB length exceeds file size")
    off = 12
    gltf = None
    chunks: list[dict[str, int]] = []
    while off + 8 <= total:
        length, ctype = struct.unpack_from("<II", data, off)
        off += 8
        payload = data[off:off + length]
        off += length
        chunks.append({"type": ctype, "length": length})
        if ctype == JSON_CHUNK:
            gltf = json.loads(payload.rstrip(b"\x00 \t\r\n").decode("utf-8"))
    if gltf is None:
        raise ValueError("GLB missing JSON chunk")
    return gltf, chunks


def load_asset(path: str | Path) -> Asset:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"unsupported asset type {suffix}; supported: {sorted(SUPPORTED)}")
    if suffix == ".gltf":
        gltf = json.loads(p.read_text(encoding="utf-8"))
        return Asset(p, "gltf", gltf, p.stat().st_size, [])
    gltf, chunks = _read_glb(p)
    kind = "vrm" if suffix == ".vrm" else "glb"
    return Asset(p, kind, gltf, p.stat().st_size, chunks)


def _accessor(gltf: dict[str, Any], idx: int | None) -> dict[str, Any] | None:
    if idx is None:
        return None
    arr = gltf.get("accessors", [])
    return arr[idx] if 0 <= idx < len(arr) else None


def _semantic_hint(name: str | None) -> dict[str, Any]:
    s = (name or "").lower().replace("-", "_").replace(" ", "_")
    rules = [
        ("hair", ["hair", "bang", "pony", "braid"]),
        ("head", ["head", "face", "skull"]),
        ("garment", ["cloth", "shirt", "dress", "coat", "robe", "jacket", "skirt", "garment"]),
        ("left_arm", ["left_arm", "l_arm", "arm_l"]),
        ("right_arm", ["right_arm", "r_arm", "arm_r"]),
        ("left_leg", ["left_leg", "l_leg", "leg_l"]),
        ("right_leg", ["right_leg", "r_leg", "leg_r"]),
        ("body", ["body", "torso", "chest", "hips", "pelvis"]),
        ("accessory", ["crown", "book", "weapon", "accessory", "prop", "hat", "bag"]),
        ("effect", ["effect", "magic", "aura", "ring", "spell"]),
    ]
    for label, keys in rules:
        if any(k in s for k in keys):
            return {"label": label, "confidence": 0.72, "source": "node-name-heuristic"}
    return {"label": "unknown", "confidence": 0.0, "source": "unresolved"}


def extract_ir(asset_or_path: Asset | str | Path) -> dict[str, Any]:
    asset = asset_or_path if isinstance(asset_or_path, Asset) else load_asset(asset_or_path)
    gltf = asset.gltf
    meshes = gltf.get("meshes", [])
    nodes = gltf.get("nodes", [])
    materials = gltf.get("materials", [])
    skins = gltf.get("skins", [])
    animations = gltf.get("animations", [])
    extensions_used = gltf.get("extensionsUsed", []) or []
    primitives: list[dict[str, Any]] = []
    components: list[dict[str, Any]] = []
    total_vertices = total_indices = total_faces = 0
    gmin = [math.inf, math.inf, math.inf]
    gmax = [-math.inf, -math.inf, -math.inf]
    bbox_samples = 0

    for mi, mesh in enumerate(meshes):
        mname = mesh.get("name") or f"mesh-{mi}"
        for pi, prim in enumerate(mesh.get("primitives", [])):
            pos = _accessor(gltf, (prim.get("attributes") or {}).get("POSITION"))
            ind = _accessor(gltf, prim.get("indices"))
            vc = int((pos or {}).get("count", 0))
            ic = int((ind or {}).get("count", 0))
            mode = prim.get("mode", 4)
            faces = ic // 3 if mode == 4 and ic else (vc // 3 if mode == 4 else None)
            total_vertices += vc
            total_indices += ic
            if faces is not None:
                total_faces += faces
            pmin, pmax = (pos or {}).get("min"), (pos or {}).get("max")
            if pmin and pmax and len(pmin) >= 3 and len(pmax) >= 3:
                for k in range(3):
                    gmin[k] = min(gmin[k], float(pmin[k]))
                    gmax[k] = max(gmax[k], float(pmax[k]))
                bbox_samples += 1
            primitives.append({
                "mesh_index": mi,
                "primitive_index": pi,
                "name": mname,
                "vertices": vc,
                "indices": ic,
                "faces": faces,
                "material_index": prim.get("material"),
                "morph_target_count": len(prim.get("targets", []) or []),
                "semantic_candidate": _semantic_hint(mname),
            })

    for ni, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        mi = node["mesh"]
        name = node.get("name") or (meshes[mi].get("name") if 0 <= mi < len(meshes) else None) or f"node-{ni}"
        components.append({
            "node_index": ni,
            "mesh_index": mi,
            "name": name,
            "children": node.get("children", []),
            "skin": node.get("skin"),
            "translation": node.get("translation"),
            "rotation": node.get("rotation"),
            "scale": node.get("scale"),
            "semantic_candidate": _semantic_hint(name),
        })

    bbox = None
    if bbox_samples:
        bbox = {
            "min_local_untransformed": gmin,
            "max_local_untransformed": gmax,
            "extent_local_untransformed": [gmax[i] - gmin[i] for i in range(3)],
            "warning": "accessor min/max aggregated without node transforms in model2ir v0.1",
        }

    resolved = [c for c in components if c["semantic_candidate"]["label"] != "unknown"]
    unresolved = [c for c in components if c["semantic_candidate"]["label"] == "unknown"]
    return {
        "schema": "model2ir-character-ir/v0.1",
        "source_kind": asset.kind,
        "evidence_class": "observed_3d_asset",
        "source": {"name": asset.path.name, "bytes": asset.bytes_size},
        "structural_ir": {
            "geometry": {
                "mesh_count": len(meshes),
                "primitive_count": len(primitives),
                "component_count": len(components),
                "vertices_sum": total_vertices,
                "indices_sum": total_indices,
                "triangle_faces_sum": total_faces,
                "material_count": len(materials),
                "skin_count": len(skins),
                "animation_count": len(animations),
                "bbox": bbox,
            },
            "scene_count": len(gltf.get("scenes", []) or []),
            "node_count": len(nodes),
            "extensions_used": extensions_used,
            "components": components,
            "primitives": primitives,
            "skins": skins,
        },
        "semantic_ir": {
            "candidates": [c for c in components if c["semantic_candidate"]["label"] != "unknown"],
            "unresolved": unresolved,
            "resolved_component_count": len(resolved),
            "unresolved_component_count": len(unresolved),
        },
        "relations": {
            "node_child_edges": [
                {"parent": i, "child": child}
                for i, node in enumerate(nodes)
                for child in (node.get("children", []) or [])
            ],
            "skin_bindings": [
                {"node_index": c["node_index"], "skin_index": c["skin"]}
                for c in components if c.get("skin") is not None
            ],
        },
        "provenance": {
            "extractor": "model2ir/v0.1",
            "chunks": asset.chunks,
            "truth_policy": "geometry/scene structure may be factual; semantic labels are hypotheses until corroborated or confirmed",
        },
    }


def _semantic_labels(ir: dict[str, Any]) -> set[str]:
    if ir.get("schema") == "model2ir-character-ir/v0.1":
        comps = ir.get("semantic_ir", {}).get("candidates", []) or []
        return {c.get("semantic_candidate", {}).get("label") for c in comps if c.get("semantic_candidate", {}).get("label") not in (None, "unknown")}
    parts = ir.get("inferred", {}).get("parts", []) or []
    out: set[str] = set()
    for p in parts:
        if isinstance(p, str):
            out.add(p)
        elif isinstance(p, dict):
            x = p.get("id") or p.get("part") or p.get("name")
            if x:
                out.add(x)
    return out


def diff_ir(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    la, lb = _semantic_labels(a), _semantic_labels(b)
    ga = a.get("structural_ir", {}).get("geometry", {})
    gb = b.get("structural_ir", {}).get("geometry", {})
    numeric = {}
    for k in sorted(set(ga) & set(gb)):
        if isinstance(ga[k], (int, float)) and isinstance(gb[k], (int, float)):
            numeric[k] = {"a": ga[k], "b": gb[k], "delta": gb[k] - ga[k]}
    return {
        "schema": "model2ir-diff/v0.1",
        "semantic": {
            "shared": sorted(la & lb),
            "only_a": sorted(la - lb),
            "only_b": sorted(lb - la),
            "jaccard": round(len(la & lb) / len(la | lb), 4) if la | lb else 1.0,
        },
        "geometry_numeric": numeric,
    }


def reconcile_ir(image_ir: dict[str, Any], model_ir: dict[str, Any]) -> dict[str, Any]:
    img = _semantic_labels(image_ir)
    mdl = _semantic_labels(model_ir)
    unresolved = model_ir.get("semantic_ir", {}).get("unresolved", []) or []
    return {
        "schema": "model2ir-reconciliation/v0.1",
        "matched": sorted(img & mdl),
        "image_only": sorted(img - mdl),
        "model_candidates_only": sorted(mdl - img),
        "unresolved_model_components": unresolved,
        "automatic_canonical_promotions": [],
        "policy": "3D-derived semantics remain candidate evidence until corroborated or user-confirmed",
        "semantic_recovery_ratio": round(len(img & mdl) / len(img), 4) if img else 1.0,
    }


def score_roundtrip(source_ir: dict[str, Any], recovered_ir: dict[str, Any]) -> dict[str, Any]:
    d = diff_ir(source_ir, recovered_ir)
    return {
        "schema": "model2ir-roundtrip-score/v0.1",
        "semantic_preservation": d["semantic"]["jaccard"],
        "diff": d,
    }
