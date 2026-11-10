"""Bounded read adapter for the EXISTING AgentOS Project Store.

This is only a local-project snapshot. It is NOT an Atlas/global inventory
attestation and cannot authorize creation of anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from .gaia_intake import Asset, Decision, Disposition, Proposal, review


@dataclass(frozen=True)
class LocalProjectEvidence:
    assets: tuple[Asset, ...]
    provenance: str
    errors: tuple[str, ...]


def read_local_projects() -> LocalProjectEvidence:
    from . import project_store
    from . import config

    root = config.PROJECTS_DIR
    if not root.is_dir():
        return LocalProjectEvidence((), str(root), ("project_store_missing",))
    try:
        dirs = tuple(p for p in root.iterdir() if p.is_dir())
        projects = tuple(project_store.list_projects())
    except (OSError, ValueError) as exc:
        return LocalProjectEvidence((), str(root), ("project_store_read_failed:" + type(exc).__name__,))
    if len(projects) != len(dirs):
        return LocalProjectEvidence((), str(root), ("unreadable_project_declaration",))
    ids = [p.project_id for p in projects]
    if len(ids) != len(set(ids)):
        return LocalProjectEvidence((), str(root), ("duplicate_project_id",))
    assets = tuple(Asset(
        canonical_id="project://" + p.project_id,
        kind="project",
        aliases=(p.display_name,),
        capabilities=tuple(p.capabilities_provided),
    ) for p in projects)
    return LocalProjectEvidence(assets, str(root), ())


def review_existing_local_project(
    proposal: Proposal,
    evidence: LocalProjectEvidence,
) -> Decision:
    """Find already-registered parents, never conclude a new project is safe.

    The global source-of-truth may include projects outside this node, so
    unmatched proposals remain NEEDS_EVIDENCE pending Atlas reconciliation.
    """
    if evidence.errors or not evidence.provenance:
        return Decision(Disposition.NEEDS_EVIDENCE, None,
                        evidence.errors or ("missing_snapshot_provenance",))
    candidate = review(proposal, evidence.assets, registry_complete=True)
    if candidate.disposition in (Disposition.EXTEND_PROJECT, Disposition.USE_EXISTING):
        return Decision(candidate.disposition, candidate.canonical_parent,
                        ("local_project_store:" + evidence.provenance,) + candidate.evidence,
                        requires_authorization=True)
    if candidate.disposition == Disposition.NEEDS_HUMAN_APPROVAL and not proposal.requests_new_trust_boundary:
        return Decision(Disposition.NEEDS_EVIDENCE, None,
                        ("global_registry_not_checked",))
    return candidate
