"""Vendor-neutral stamp recognition contracts.

This capability does not know about invoices or accounting. It identifies a
physical/visual stamp, links repeated observations, and optionally resolves the
stamp to a previously confirmed entity.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class StampFingerprint:
    algorithm: str
    version: str
    value: str
    features: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StampEntity:
    stamp_id: str
    entity_id: str | None = None
    canonical_label: str | None = None
    verified_attributes: Mapping[str, Any] = field(default_factory=dict)
    status: str = "candidate"


@dataclass(frozen=True)
class StampMatch:
    decision: str
    score: float
    stamp_id: str | None = None
    entity_id: str | None = None
    reasons: tuple[str, ...] = ()
    requires_confirmation: bool = True


VALID_DECISIONS = {
    "same_stamp",
    "same_entity_new_stamp",
    "unknown_stamp",
    "uncertain",
}


def validate_match(match: StampMatch) -> None:
    if match.decision not in VALID_DECISIONS:
        raise ValueError(f"unsupported stamp decision: {match.decision}")
    if not 0.0 <= match.score <= 1.0:
        raise ValueError("stamp match score must be between 0 and 1")
    if match.decision == "same_stamp" and not match.stamp_id:
        raise ValueError("same_stamp requires stamp_id")
    if match.decision == "same_entity_new_stamp" and not match.entity_id:
        raise ValueError("same_entity_new_stamp requires entity_id")
