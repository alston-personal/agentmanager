"""Pure, fail-closed release-intent check for a future ONE-backed deployment gate.

This module does NOT grant authority to a caller's JSON. The *trusted* current
release epoch/intent must be obtained from the existing authoritative Runtime/
ONE control boundary and authenticated before entering these functions.
No I/O, clocks, mutations, fetching, or side effects occur here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


_SHA = re.compile(r"[0-9a-f]{40}\Z")
MAIN = "main"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    release_epoch: int | None = None


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def verify_release_intent(
    *,
    request: Mapping[str, Any],
    approved_intent: Mapping[str, Any] | None,
    observed_target: Mapping[str, Any] | None,
    authenticated_principal: str | None,
    now: datetime,
) -> Decision:
    """Evaluate a trusted approval and observed target epoch.

    Caller MUST independently authenticate `approved_intent`, the target epoch,
    and `authenticated_principal` through ONE/Runtime identity. NEVER derive
    any of these values from request claims or a caller-supplied approval. The result is only a preflight decision; executors still
    need a persisted CAS lease + a just-before-cutover recheck.
    """
    if not isinstance(approved_intent, Mapping):
        return Decision(False, "missing_trusted_release_intent")
    if not isinstance(observed_target, Mapping):
        return Decision(False, "missing_trusted_target_epoch")
    if now.tzinfo is None:
        return Decision(False, "invalid_verification_clock")
    if request.get("source_ref") != MAIN:
        return Decision(False, "non_main_source_forbidden")
    sha = request.get("source_commit")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        return Decision(False, "invalid_exact_source_sha")
    if approved_intent.get("schema") != "agentos.approved-release-intent/v1":
        return Decision(False, "invalid_intent_schema")
    if approved_intent.get("state") != "approved":
        return Decision(False, "release_not_approved")
    if approved_intent.get("source_ref") != MAIN:
        return Decision(False, "non_main_intent_forbidden")
    if approved_intent.get("source_commit") != sha:
        return Decision(False, "source_commit_not_approved")
    for key in ("repository", "project_id", "realm_id", "environment", "operation"):
        if not request.get(key) or request[key] != approved_intent.get(key):
            return Decision(False, "scope_mismatch_" + key)
    digest = approved_intent.get("artifact_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return Decision(False, "missing_immutable_artifact_digest")
    # The immutable artifact must be the one the trusted authority approved.
    # An approved source SHA alone cannot authorize deploying different bytes.
    if request.get("artifact_digest") != digest:
        return Decision(False, "artifact_digest_not_approved")
    if request.get("approval_receipt_id") != approved_intent.get("approval_receipt_id"):
        return Decision(False, "approval_receipt_mismatch")
    if not isinstance(approved_intent.get("approval_receipt_id"), str) or not approved_intent["approval_receipt_id"]:
        return Decision(False, "missing_approval_receipt")
    if not isinstance(approved_intent.get("authorized_principal"), str) or not approved_intent["authorized_principal"]:
        return Decision(False, "missing_authorized_principal")
    if (not isinstance(authenticated_principal, str) or not authenticated_principal
            or authenticated_principal != approved_intent["authorized_principal"]):
        return Decision(False, "principal_not_authorized")
    valid_until = _utc(approved_intent.get("expires_at"))
    if valid_until is None or now.astimezone(timezone.utc) >= valid_until:
        return Decision(False, "intent_expired")
    epoch = approved_intent.get("release_epoch")
    target_epoch = observed_target.get("release_epoch")
    if (type(epoch) is not int or epoch < 1 or
            type(target_epoch) is not int or target_epoch < 0):
        return Decision(False, "invalid_release_epoch")
    if request.get("release_epoch") != epoch:
        return Decision(False, "request_epoch_mismatch")
    if epoch <= target_epoch:
        return Decision(False, "stale_release_epoch")
    if observed_target.get("repository") != request["repository"]:
        return Decision(False, "target_repository_mismatch")
    if observed_target.get("environment") != request["environment"]:
        return Decision(False, "target_environment_mismatch")
    if observed_target.get("realm_id") != request["realm_id"]:
        return Decision(False, "target_realm_mismatch")
    return Decision(True, "preflight_eligible_requires_atomic_target_cas", epoch)
