"""Read-only Governance Directory evidence for Gaia proposal review.

Governance Directory is a query projection, not the canonical source
for roles and projects. An empty/missing directory must not be trusted
as evidence that an asset does not exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .gaia_intake import Asset, Decision, Disposition, Proposal, review
from .governance_directory import load_directory


@dataclass(frozen=True)
class DirectoryEvidence:
    assets: tuple[Asset, ...]
    provenance: str
    errors: tuple[str, ...]


def read_governance_directory(path: Path) -> DirectoryEvidence:
    if not path.is_file():
        return DirectoryEvidence((), str(path), ("directory_missing",))
    try:
        record = load_directory(path)
    except (OSError, ValueError, TypeError) as exc:
        return DirectoryEvidence((), str(path), ("directory_unreadable:" + type(exc).__name__,))
    entities = record.get("entities")
    if not isinstance(entities, dict) or not record.get("updated_at"):
        return DirectoryEvidence((), str(path), ("directory_not_attested",))
    found = []
    for key, value in entities.items():
        if not isinstance(value, dict) or value.get("id") != key:
            return DirectoryEvidence((), str(path), ("directory_identity_mismatch",))
        kind = value.get("kind")
        if kind not in ("project", "role", "capability", "node", "service", "manager", "policy", "spec", "resource"):
            return DirectoryEvidence((), str(path), ("directory_unknown_kind",))
        if value.get("state") in ("retired", "superseded"):
            continue
        meta = value.get("metadata") or {}
        if not isinstance(meta, dict):
            return DirectoryEvidence((), str(path), ("directory_invalid_metadata",))
        aliases = tuple(str(x) for x in (meta.get("aliases") or []))
        provides = tuple(str(x) for x in (value.get("provides") or []))
        found.append(Asset(key, str(kind), aliases=(str(value.get("name") or ""),) + aliases,
                           capabilities=provides))
    return DirectoryEvidence(tuple(found), str(path), ())


def review_directory_candidate(proposal: Proposal, evidence: DirectoryEvidence) -> Decision:
    """Positive existing matches can be recommended; negative matches are inconclusive.

    No global completeness proof is produced by reading a projection. New
    project creation cannot be approved by this function.
    """
    if evidence.errors or not evidence.provenance:
        return Decision(Disposition.NEEDS_EVIDENCE, None,
                        evidence.errors or ("missing_directory_provenance",))
    tentative = review(proposal, evidence.assets, registry_complete=True)
    if tentative.disposition in (Disposition.EXTEND_PROJECT, Disposition.USE_EXISTING):
        return Decision(tentative.disposition, tentative.canonical_parent,
                        ("governance_projection:" + evidence.provenance,) + tentative.evidence)
    if tentative.disposition == Disposition.NEEDS_HUMAN_APPROVAL and not proposal.requests_new_trust_boundary:
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("canonical_asset_sources_not_reconciled",))
    return tentative
