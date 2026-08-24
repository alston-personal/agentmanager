"""Governance guards for Git ref movement.

Moving an integration/base ref can absorb a pull-request head without invoking a
merge API. Treat the effect, not the API name, as the authority boundary.
"""
from __future__ import annotations

from dataclasses import dataclass


class RefGovernanceError(PermissionError):
    pass


@dataclass(frozen=True)
class RefMoveIntent:
    repository: str
    ref: str
    old_sha: str
    new_sha: str
    actor_ref: str
    reason: str
    explicit_human_approval: bool = False
    is_fast_forward: bool = True
    open_pr_head_shas: tuple[str, ...] = ()
    protected_refs: tuple[str, ...] = ("main",)
    integration_refs: tuple[str, ...] = ()

    @property
    def is_protected(self) -> bool:
        return self.ref in set(self.protected_refs) | set(self.integration_refs)

    @property
    def absorbs_open_pr_head(self) -> bool:
        return self.new_sha in self.open_pr_head_shas and self.new_sha != self.old_sha

    @property
    def merge_equivalent(self) -> bool:
        return self.is_protected and self.absorbs_open_pr_head


def authorize_ref_move(intent: RefMoveIntent) -> None:
    """Fail closed for ref effects that can bypass review/merge boundaries."""
    required = (intent.repository, intent.ref, intent.old_sha, intent.new_sha, intent.actor_ref, intent.reason)
    if any(not str(v).strip() for v in required):
        raise RefGovernanceError("REF_MOVE_DENIED: incomplete execution coordinates")
    if not intent.is_fast_forward:
        raise RefGovernanceError("REF_MOVE_DENIED: non-fast-forward requires separate break-glass authority")
    if intent.merge_equivalent and not intent.explicit_human_approval:
        raise RefGovernanceError("REF_MOVE_DENIED: merge-equivalent protected ref movement requires explicit human approval")
