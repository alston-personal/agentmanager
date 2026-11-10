"""Reconcile Gaia's local canonical Project Store with Governance Directory.

This module emits decisions only; it is not a write gate or approval issuer.
"""
from __future__ import annotations

from .gaia_intake import Decision, Disposition, Proposal
from .gaia_project_adapter import LocalProjectEvidence, review_existing_local_project
from .gaia_directory_adapter import DirectoryEvidence, review_directory_candidate


def reconcile_project_proposal(
    proposal: Proposal, local: LocalProjectEvidence, directory: DirectoryEvidence
) -> Decision:
    if local.errors or directory.errors:
        return Decision(Disposition.NEEDS_EVIDENCE, None,
                        ("incomplete_sources",) + local.errors + directory.errors)
    a = review_existing_local_project(proposal, local)
    b = review_directory_candidate(proposal, directory)
    positive = {Disposition.EXTEND_PROJECT, Disposition.USE_EXISTING}
    if a.disposition in positive and b.disposition in positive:
        if a.canonical_parent != b.canonical_parent or a.disposition != b.disposition:
            return Decision(Disposition.NEEDS_EVIDENCE, None, ("source_identity_conflict",))
        return Decision(a.disposition, a.canonical_parent,
                        a.evidence + b.evidence, requires_authorization=True)
    if a.disposition in positive or b.disposition in positive:
        return Decision(Disposition.NEEDS_EVIDENCE, None,
                        ("source_missing_correspondence",) + a.evidence + b.evidence)
    if a.disposition == Disposition.NEEDS_HUMAN_APPROVAL or b.disposition == Disposition.NEEDS_HUMAN_APPROVAL:
        return Decision(Disposition.NEEDS_HUMAN_APPROVAL, None,
                        ("review_new_trust_boundary",))
    return Decision(Disposition.NEEDS_EVIDENCE, None,
                    ("atlas_global_inventory_pending",))
