"""Hermes evidence-only handoff proposals; ONE remains the only authority for work assignment."""
from __future__ import annotations

from typing import Any

SCHEMA = "agentos.hermes-handoff-proposal/v1"
ROUTES = {
    "existing_equivalent": "research.hermes",
    "existing_owner": "canonical_issue_owner",
    "needs_specification": "sector.weaver",
    "clear_implementation": "sector.paw",
    "license_or_security_risk": "sector.claw",
    "monitor_only": "research.hermes",
}
VALID_CLASSES = {
    "EXISTING_EQUIVALENT", "REUSABLE_COMPONENT", "DESIGN_REFERENCE",
    "EXPERIMENT_CANDIDATE", "INCOMPATIBLE", "REJECTED",
}


def handoff_proposal(
    *,
    candidate: dict[str, Any],
    existing_owner_ref: str | None,
    gap_confirmed: bool,
    license_review_passed: bool,
    security_review_passed: bool,
    implementation_spec_ready: bool,
) -> dict[str, Any]:
    """Suggest a destination without writing a task, authorizing execution or approving work."""
    classification = candidate.get("classification")
    if classification not in VALID_CLASSES:
        raise ValueError("unknown_hermes_classification")
    repo = candidate.get("repo")
    source = candidate.get("source_url")
    if not isinstance(repo, str) or not repo:
        raise ValueError("missing_repository")
    if source != "https://github.com/" + repo:
        raise ValueError("source_identity_mismatch")
    if existing_owner_ref is not None and (
        not isinstance(existing_owner_ref, str)
        or not existing_owner_ref.startswith("github:alston-personal/agentmanager#")
    ):
        raise ValueError("invalid_owner_reference")

    if classification in {"REJECTED", "INCOMPATIBLE", "DESIGN_REFERENCE"}:
        reason = "monitor_only"
    elif classification == "EXISTING_EQUIVALENT" or not gap_confirmed:
        reason = "existing_equivalent"
    elif existing_owner_ref:
        reason = "existing_owner"
    elif not license_review_passed or not security_review_passed:
        reason = "license_or_security_risk"
    elif implementation_spec_ready:
        reason = "clear_implementation"
    else:
        reason = "needs_specification"

    return {
        "schema": SCHEMA,
        "repo": repo,
        "source_url": source,
        "classification": classification,
        "route_reason": reason,
        "suggested_owner": ROUTES[reason],
        "existing_owner_ref": existing_owner_ref,
        "gap_confirmed": gap_confirmed,
        "license_review_passed": license_review_passed,
        "security_review_passed": security_review_passed,
        "proposal_only": True,
        "work_item_created": False,
        "execution_authorized": False,
    }
