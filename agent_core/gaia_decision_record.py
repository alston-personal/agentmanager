"""Immutable, content-addressed Gaia review evidence — NOT an approval credential.

A hash detects accidental record alteration but is not a signature or authority.
The authoritative Creation Gate must separately verify actor, snapshot freshness
and an approval decision from the existing governance authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from .gaia_intake import Decision, Disposition, Proposal


SCHEMA = "agentos.gaia-review/v1"


@dataclass(frozen=True)
class ReviewRecord:
    schema: str
    proposal: dict
    decision: dict
    source_refs: tuple[str, ...]
    reviewed_at: str
    content_hash: str
    authority: str = "none"


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def issue_review_record(
    proposal: Proposal,
    decision: Decision,
    *,
    source_refs: tuple[str, ...],
    reviewed_at: str,
) -> ReviewRecord:
    """Bind an informational decision to explicit external source references.

    No new-project approval can be produced here; this code never grants
    authorization and must not be treated as an execution receipt.
    """
    if not source_refs or any(not isinstance(s, str) or not s.strip() for s in source_refs):
        raise ValueError("source_refs_required")
    if len(set(source_refs)) != len(source_refs):
        raise ValueError("duplicate_source_ref")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_review_time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    p = {
        "title": proposal.title,
        "kind": proposal.kind,
        "related_asset_ids": list(proposal.related_asset_ids),
        "required_capabilities": list(proposal.required_capabilities),
        "requests_new_trust_boundary": proposal.requests_new_trust_boundary,
    }
    d = {
        "disposition": decision.disposition.value,
        "canonical_parent": decision.canonical_parent,
        "evidence": list(decision.evidence),
        "requires_authorization": decision.requires_authorization,
    }
    fields = dict(schema=SCHEMA, proposal=p, decision=d,
                  source_refs=list(source_refs), reviewed_at=parsed.isoformat(),
                  authority="none")
    digest = sha256(_canonical(fields)).hexdigest()
    return ReviewRecord(SCHEMA, p, d, source_refs, parsed.isoformat(), digest)


def verify_review_record(record: ReviewRecord) -> bool:
    """Verify structure + content integrity, not provenance or permission."""
    try:
        if record.schema != SCHEMA or record.authority != "none":
            return False
        if len(record.content_hash) != 64 or not record.source_refs:
            return False
        if record.decision.get("disposition") not in {d.value for d in Disposition}:
            return False
        if record.decision.get("requires_authorization") is not True:
            return False
        # Recompute the exact canonical representation, excluding content_hash.
        fields = asdict(record)
        digest = fields.pop("content_hash")
        fields["source_refs"] = list(fields["source_refs"])
        return sha256(_canonical(fields)).hexdigest() == digest
    except (TypeError, ValueError, AttributeError):
        return False
