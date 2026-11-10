"""Gaia -> existing Completion Controller handoff, with explicit admission boundary.

A reviewed idea is NOT authorized executable work. Build a typed proposal
envelope first; registering it requires an independently trusted admission
callback. Gaia cannot choose an executor, command, credential, or owner.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
import re
from typing import Callable

from .gaia_decision_record import ReviewRecord, verify_review_record


class GaiaHandoffDenied(PermissionError):
    pass


def propose_existing_project_work(
    record: ReviewRecord,
    *,
    source_issue_url: str,
    workspace: str,
) -> dict:
    """Prepare, but do not register, a bounded Work Intake proposal.

    The next_action is a governance review action, never an arbitrary
    natural-language command from an untrusted incoming proposal.
    """
    if not verify_review_record(record):
        raise GaiaHandoffDenied("invalid_review_record")
    decision = record.decision
    if decision.get("disposition") != "EXTEND_PROJECT":
        raise GaiaHandoffDenied("handoff_requires_existing_project_extension")
    parent = decision.get("canonical_parent")
    if not isinstance(parent, str) or not parent.startswith("project://"):
        raise GaiaHandoffDenied("existing_project_parent_required")
    parsed = urlsplit(source_issue_url)
    if (parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*", parsed.path)):
        raise GaiaHandoffDenied("canonical_issue_url_required")
    if not workspace or not Path(workspace).is_absolute():
        raise GaiaHandoffDenied("absolute_workspace_required")
    project_id = parent.removeprefix("project://")
    if not project_id or "/" in project_id or "\\" in project_id:
        raise GaiaHandoffDenied("invalid_project_id")
    return {
        "schema": "agentos.work-intake/v1",
        # Stable across re-reviews. Do not key accepted work by reviewed_at.
        "work_id": "gaia-review-" + sha256((parent + ":" + source_issue_url).encode()).hexdigest()[:24],
        "project_id": project_id,
        "title": "Review scoped extension proposal for " + project_id,
        "next_action": "Confirm canonical owner, authorized scope, dependencies and acceptance for Gaia proposal review " + record.content_hash,
        "acceptance": [
            "Canonical parent project and owner are confirmed from current registries",
            "An independently authorized scoped implementation task is recorded, or a verified blocker is returned",
        ],
        "source": source_issue_url,
        "workspace": workspace,
    }


def admit_existing_project_work(
    state_path: Path,
    record: ReviewRecord,
    envelope: dict,
    *,
    verify_intake_authority: Callable[[dict], bool],
) -> dict:
    """Hand off only after the surrounding trusted runtime admits this work.

    The callback MUST be bound to an authenticated ONE policy decision in
    production, never simply supplied by an untrusted requester.
    """
    if not isinstance(envelope, dict):
        raise GaiaHandoffDenied("invalid_intake_envelope")
    expected = propose_existing_project_work(
        record,
        source_issue_url=str(envelope.get("source") or ""),
        workspace=str(envelope.get("workspace") or ""),
    )
    if envelope != expected:
        raise GaiaHandoffDenied("intake_envelope_mismatch")
    if not callable(verify_intake_authority) or verify_intake_authority(expected) is not True:
        raise GaiaHandoffDenied("intake_not_authorized")
    # This existing API assigns role://completion.controller, not the caller.
    from scripts.work_completion import register_intake_envelope
    return register_intake_envelope(state_path, envelope)
