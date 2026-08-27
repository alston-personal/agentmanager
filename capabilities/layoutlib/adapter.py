"""LayoutLib -> AgentOS capability adapter.

LayoutLib remains a pure library. This adapter translates observable LayoutLab
results into AgentOS capability experience. It deliberately accepts abstract
features and correction metrics rather than raw image bytes.
"""
from __future__ import annotations

from typing import Any, Mapping

from agentos_node.capability_runtime import CapabilityExperience


PROFILE_CAPABILITY = "layoutlib.profile-detection"
RECONSTRUCTION_CAPABILITY = "layoutlib.layout-reconstruction"


def correction_cost(metrics: Mapping[str, Any]) -> float:
    """Reference human-correction cost used as a learning outcome.

    Weights are intentionally explicit and versionable. They can later be
    learned/evaluated, but changing them is itself a capability-policy change.
    """
    return (
        float(metrics.get("walls_added", 0)) * 1.0
        + float(metrics.get("walls_deleted", 0)) * 1.0
        + float(metrics.get("erase_length_px", 0)) / 100.0
        + float(metrics.get("reanalyze_count", 0)) * 0.5
        + float(metrics.get("manual_parameter_changes", 0)) * 0.25
    )


def quality_from_correction_cost(cost: float) -> float:
    # Smooth monotonic score: zero edits ~= 1.0, more correction -> lower quality.
    return 1.0 / (1.0 + max(0.0, float(cost)))


def make_profile_experience(
    *,
    node_id: str,
    profile_features: Mapping[str, Any],
    policy_used: Mapping[str, Any],
    correction_metrics: Mapping[str, Any],
    accepted: bool,
    provenance: Mapping[str, Any] | None = None,
) -> CapabilityExperience:
    cost = correction_cost(correction_metrics)
    return CapabilityExperience(
        capability_id=PROFILE_CAPABILITY,
        node_id=node_id,
        observation={"profile_features": dict(profile_features)},
        policy_used=dict(policy_used),
        outcome={
            "accepted": bool(accepted),
            "correction_cost": cost,
            "quality": quality_from_correction_cost(cost) if accepted else 0.0,
            **dict(correction_metrics),
        },
        provenance=dict(provenance or {}),
    )


def make_reconstruction_experience(
    *,
    node_id: str,
    component_receipts: Mapping[str, str],
    correction_metrics: Mapping[str, Any],
    accepted: bool,
    provenance: Mapping[str, Any] | None = None,
) -> CapabilityExperience:
    """Experience owned by the composite capability, not its child libraries.

    This records how detection + geometry were composed end-to-end. Child
    capabilities keep their own experiences separately.
    """
    cost = correction_cost(correction_metrics)
    return CapabilityExperience(
        capability_id=RECONSTRUCTION_CAPABILITY,
        node_id=node_id,
        observation={"component_receipts": dict(component_receipts)},
        policy_used={},
        outcome={
            "accepted": bool(accepted),
            "correction_cost": cost,
            "quality": quality_from_correction_cost(cost) if accepted else 0.0,
            **dict(correction_metrics),
        },
        provenance=dict(provenance or {}),
    )
