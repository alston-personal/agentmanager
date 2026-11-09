"""Guarded canonical project-creation entrypoint for Gaia (#420).

The caller MUST supply a trusted authorization verifier, not a boolean,
a hash, or Gaia's own informational review record. This helper never
self-authorizes creation and leaves the legacy entrypoint untouched until
its callers are migrated and audited.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .gaia_decision_record import ReviewRecord, verify_review_record
from .project_store import CanonicalProjectRegistration, register_canonical_project


@dataclass(frozen=True)
class CreationAuthorization:
    decision_hash: str
    project_id: str
    actor_id: str
    expires_at: str
    approval_id: str


class CreationDenied(PermissionError):
    pass


def register_reviewed_project(
    registration: CanonicalProjectRegistration,
    review: ReviewRecord,
    authorization: CreationAuthorization,
    *,
    verify_authorization: Callable[[CreationAuthorization], bool],
) -> dict:
    """Persist a new project only after independently validated approval.

    The verifier is an injected trust-boundary interface; the *production*
    caller must bind it to a trusted ONE authorization source. Callers
    cannot use the informational review hash as an approval credential.
    """
    registration.validate()
    if not verify_review_record(review):
        raise CreationDenied("invalid_review_record")
    if review.proposal.get("kind") != "project":
        raise CreationDenied("review_kind_mismatch")
    if review.proposal.get("title", "").strip().casefold() != registration.display_name.strip().casefold():
        raise CreationDenied("review_title_scope_mismatch")
    if review.proposal.get("related_asset_ids"):
        raise CreationDenied("existing_related_assets_require_reconciliation")
    if review.proposal.get("requests_new_trust_boundary") and not authorization.actor_id:
        raise CreationDenied("trust_boundary_requires_actor")
    try:
        review_time = datetime.fromisoformat(review.reviewed_at.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CreationDenied("invalid_review_time") from exc
    now = datetime.now(timezone.utc)
    if review_time.tzinfo is None or review_time.utcoffset() is None:
        raise CreationDenied("review_timezone_required")
    if review_time.astimezone(timezone.utc) > now:
        raise CreationDenied("future_review_record")
    if (now - review_time.astimezone(timezone.utc)).total_seconds() > 86400:
        raise CreationDenied("stale_review_record")
    if review.decision.get("disposition") != "NEEDS_HUMAN_APPROVAL":
        raise CreationDenied("review_is_not_new_project_proposal")
    if review.decision.get("canonical_parent") is not None:
        raise CreationDenied("existing_parent_requires_extension")
    if authorization.decision_hash != review.content_hash:
        raise CreationDenied("review_hash_mismatch")
    if authorization.project_id != registration.project_id:
        raise CreationDenied("project_scope_mismatch")
    if not authorization.actor_id or not authorization.approval_id:
        raise CreationDenied("missing_authority_identity")
    try:
        expiry = datetime.fromisoformat(authorization.expires_at.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise CreationDenied("invalid_expiry") from exc
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise CreationDenied("timezone_required")
    if datetime.now(timezone.utc) >= expiry.astimezone(timezone.utc):
        raise CreationDenied("approval_expired")
    if not callable(verify_authorization) or verify_authorization(authorization) is not True:
        raise CreationDenied("approval_not_verified")
    return register_canonical_project(registration, replace=False)
