"""Plan safe reconciliation of Node-local cognition into AgentOS.

"回歸一" is intentionally not raw-data centralization.  The Node exposes
metadata/provenance descriptors, AgentOS classifies them, and only governed
promotion may later change durable project/cross-project cognition.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable


RECONCILIATION_SCHEMA = "agentos.node-reconciliation/v1"


class ReconciliationDisposition(str, Enum):
    LINK_EXISTING = "link_existing"
    CANDIDATE_PROMOTION = "candidate_promotion"
    CONTRADICTION_REVIEW = "contradiction_review"
    SUPERSESSION_REVIEW = "supersession_review"
    KEEP_NODE_LOCAL = "keep_node_local"
    BLOCK_SENSITIVE = "block_sensitive"


@dataclass(frozen=True)
class LocalCognitionDescriptor:
    local_ref: str
    content_hash: str
    kind: str
    provenance: str
    project_id: str | None = None
    supersedes_hash: str | None = None
    sensitive: bool = False
    node_local_only: bool = False

    def __post_init__(self) -> None:
        if not self.local_ref.strip() or not self.content_hash.strip() or not self.kind.strip() or not self.provenance.strip():
            raise ValueError("local cognition identity/provenance fields are required")


@dataclass(frozen=True)
class ReconciliationCandidate:
    local_ref: str
    content_hash: str
    disposition: ReconciliationDisposition
    reason: str
    authority_required: bool


@dataclass(frozen=True)
class NodeReconciliationPlan:
    node_id: str
    observed_at: str
    candidates: tuple[ReconciliationCandidate, ...]
    schema_version: str = RECONCILIATION_SCHEMA

    @property
    def plan_id(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "node_id": self.node_id,
            "observed_at": self.observed_at,
            "candidates": [candidate.__dict__ for candidate in self.candidates],
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
        return "nrec_" + sha256(raw.encode("utf-8")).hexdigest()[:32]


def plan_node_reconciliation(
    *,
    node_id: str,
    observed_at: str,
    local_items: Iterable[LocalCognitionDescriptor],
    known_hashes: set[str],
    contradicted_hashes: set[str] | None = None,
) -> NodeReconciliationPlan:
    """Classify descriptors without copying content or mutating canonical cognition."""

    contradicted = contradicted_hashes or set()
    candidates: list[ReconciliationCandidate] = []
    for item in sorted(local_items, key=lambda value: (value.content_hash, value.local_ref)):
        if item.sensitive:
            disposition = ReconciliationDisposition.BLOCK_SENSITIVE
            reason = "sensitive material stays outside reconciliation transport"
            authority_required = False
        elif item.node_local_only:
            disposition = ReconciliationDisposition.KEEP_NODE_LOCAL
            reason = "descriptor is explicitly scoped to this Node"
            authority_required = False
        elif item.content_hash in known_hashes:
            disposition = ReconciliationDisposition.LINK_EXISTING
            reason = "content hash already exists in canonical cognition"
            authority_required = False
        elif item.content_hash in contradicted:
            disposition = ReconciliationDisposition.CONTRADICTION_REVIEW
            reason = "descriptor conflicts with known cognition and must retain both sides"
            authority_required = True
        elif item.supersedes_hash and item.supersedes_hash in known_hashes:
            disposition = ReconciliationDisposition.SUPERSESSION_REVIEW
            reason = "descriptor claims to supersede known cognition"
            authority_required = True
        else:
            disposition = ReconciliationDisposition.CANDIDATE_PROMOTION
            reason = "new provenance-bearing cognition may be proposed for governed promotion"
            authority_required = True

        candidates.append(
            ReconciliationCandidate(
                local_ref=item.local_ref,
                content_hash=item.content_hash,
                disposition=disposition,
                reason=reason,
                authority_required=authority_required,
            )
        )

    return NodeReconciliationPlan(node_id=node_id, observed_at=observed_at, candidates=tuple(candidates))
