"""Pure, read-only Gaia proposal classifier; never grants creation or execution authority.

The caller must provide a current canonical asset snapshot. Missing or ambiguous
registry evidence fails closed; proposals are not WorkItems or authorizations.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Disposition(str, Enum):
    USE_EXISTING = "USE_EXISTING"
    EXTEND_PROJECT = "EXTEND_PROJECT"
    EXTRACT_SHARED_CAPABILITY = "EXTRACT_SHARED_CAPABILITY"
    NEEDS_HUMAN_APPROVAL = "NEEDS_HUMAN_APPROVAL"
    NEEDS_EVIDENCE = "NEEDS_EVIDENCE"


@dataclass(frozen=True)
class Asset:
    canonical_id: str
    kind: str
    aliases: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class Proposal:
    title: str
    kind: str
    related_asset_ids: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    requests_new_trust_boundary: bool = False


@dataclass(frozen=True)
class Decision:
    disposition: Disposition
    canonical_parent: str | None
    evidence: tuple[str, ...]
    requires_authorization: bool = True


def review(proposal: Proposal, assets: Iterable[Asset], *, registry_complete: bool) -> Decision:
    """Recommend a route, not create anything. Explicit known IDs outrank names.

    Only existing capability reuse may be recommended without a new authorization;
    that recommendation itself never authorizes any action.
    """
    snapshot = tuple(assets)
    if not registry_complete:
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("registry_incomplete",))
    if not proposal.title.strip() or not proposal.kind.strip():
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("invalid_proposal",))
    ids = {a.canonical_id for a in snapshot}
    if len(ids) != len(snapshot) or any(not a.canonical_id for a in snapshot):
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("ambiguous_registry_identity",))
    related = set(proposal.related_asset_ids)
    if related - ids:
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("unknown_related_asset",))
    if proposal.requests_new_trust_boundary:
        return Decision(Disposition.NEEDS_HUMAN_APPROVAL, None, ("new_trust_boundary",))

    matches = [a for a in snapshot if a.canonical_id in related]
    if not matches:
        title = proposal.title.strip().casefold()
        matches = [a for a in snapshot if title == a.canonical_id.casefold()
                   or title in {alias.casefold() for alias in a.aliases}]
    if len(matches) > 1:
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("multiple_canonical_matches",))
    if matches:
        asset = matches[0]
        if proposal.kind == "project" and asset.kind == "project":
            return Decision(Disposition.EXTEND_PROJECT, asset.canonical_id,
                            ("existing_project:" + asset.canonical_id,))
        if proposal.kind == asset.kind:
            return Decision(Disposition.USE_EXISTING, asset.canonical_id,
                            ("existing_asset:" + asset.canonical_id,))

    required = set(proposal.required_capabilities)
    providers = [a for a in snapshot if a.kind == "capability" and required and
                 required.issubset(set(a.capabilities))]
    if len(providers) == 1:
        return Decision(Disposition.USE_EXISTING, providers[0].canonical_id,
                        ("capability_provider:" + providers[0].canonical_id,))
    if len(providers) > 1:
        return Decision(Disposition.NEEDS_EVIDENCE, None, ("multiple_capability_providers",))
    return Decision(Disposition.NEEDS_HUMAN_APPROVAL, None,
                    ("no_verified_existing_equivalent",))
