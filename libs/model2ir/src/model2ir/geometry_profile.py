from __future__ import annotations

import math
from typing import Any

GEOMETRY_PROFILE_SCHEMA = "model2ir-geometry-profile/v0.9.1"
PLANAR_THIN_AXIS_RATIO_MAX = 0.15
PLANAR_MIDDLE_AXIS_RATIO_MIN = 0.55
VOLUMETRIC_THIN_AXIS_RATIO_MIN = 0.35
ELONGATED_MIDDLE_AXIS_RATIO_MAX = 0.35


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bbox_extents(model_ir: dict[str, Any]) -> list[float] | None:
    bbox = ((model_ir.get("structural_ir") or {}).get("geometry") or {}).get("bbox") or {}
    raw = bbox.get("extent_local_untransformed")
    if not isinstance(raw, list) or len(raw) < 3:
        return None
    try:
        extents = [float(raw[i]) for i in range(3)]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) and x >= 0.0 for x in extents):
        return None
    return extents


def profile_asset_structure(model_ir: dict[str, Any]) -> dict[str, Any]:
    """Summarize geometric dimensionality and structural strength without inventing semantics.

    The profile deliberately keeps measured facts separate from heuristic interpretation.
    In particular, a thin unrigged mesh can be called planar/relief-like evidence, but it
    is never promoted to humanoid structure merely because its silhouette looks human.
    """

    geometry = (model_ir.get("structural_ir") or {}).get("geometry") or {}
    semantic = model_ir.get("semantic_evidence_v03") or {}
    skeleton = semantic.get("skeleton") or {}

    extents = _bbox_extents(model_ir)
    thin_axis_ratio = None
    middle_axis_ratio = None
    shape_hint = "unknown"
    unresolved: list[str] = []

    if extents is None:
        unresolved.append("bbox-extents-unavailable")
    else:
        ordered = sorted(extents)
        longest = ordered[-1]
        if longest <= 0.0:
            unresolved.append("bbox-has-zero-longest-axis")
        else:
            thin_axis_ratio = ordered[0] / longest
            middle_axis_ratio = ordered[1] / longest
            if (
                thin_axis_ratio <= PLANAR_THIN_AXIS_RATIO_MAX
                and middle_axis_ratio >= PLANAR_MIDDLE_AXIS_RATIO_MIN
            ):
                shape_hint = "planar-or-relief-like"
            elif thin_axis_ratio >= VOLUMETRIC_THIN_AXIS_RATIO_MIN:
                shape_hint = "volumetric-like"
            elif middle_axis_ratio <= ELONGATED_MIDDLE_AXIS_RATIO_MAX:
                shape_hint = "elongated-or-linear-like"
            else:
                shape_hint = "anisotropic-3d"

    skin_count = _safe_int(geometry.get("skin_count"))
    joint_count = _safe_int(skeleton.get("joint_count"))
    component_count = _safe_int(geometry.get("component_count"))

    reasons: list[str] = []
    if shape_hint == "planar-or-relief-like":
        reasons.append("thin-axis-geometry")
    if skin_count == 0:
        reasons.append("no-skin")
    if joint_count == 0:
        reasons.append("no-joints")
    if component_count <= 1:
        reasons.append("single-or-zero-mesh-component")

    if (
        shape_hint == "planar-or-relief-like"
        and skin_count == 0
        and joint_count == 0
        and component_count <= 1
    ):
        structural_signal = "weak"
    elif skin_count > 0 or joint_count >= 12:
        structural_signal = "rigged-or-structured"
    else:
        structural_signal = "indeterminate"

    return {
        "schema": GEOMETRY_PROFILE_SCHEMA,
        "observed": {
            "bbox_extent_local_untransformed": extents,
            "mesh_count": _safe_int(geometry.get("mesh_count")),
            "primitive_count": _safe_int(geometry.get("primitive_count")),
            "component_count": component_count,
            "skin_count": skin_count,
            "joint_count": joint_count,
            "animation_count": _safe_int(geometry.get("animation_count")),
        },
        "inferred": {
            "shape_hint": shape_hint,
            "thin_axis_ratio": round(thin_axis_ratio, 6) if thin_axis_ratio is not None else None,
            "middle_axis_ratio": round(middle_axis_ratio, 6) if middle_axis_ratio is not None else None,
            "structural_signal": structural_signal,
            "reasons": reasons,
        },
        "unresolved": unresolved,
        "policy": (
            "bbox anisotropy and rig presence are evidence only; planar/relief-like or weak-structure "
            "classification must not promote humanoid bones, parts, or canonical truth"
        ),
    }
