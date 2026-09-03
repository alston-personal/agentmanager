"""Governed ONE Experience discovery/hydration primitives.

Experience is a projection over canonical state/evidence, not a fourth source of
truth. This module intentionally performs deterministic filtering/projection only;
it does not grant execution authority and it does not ingest raw conversation text.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence


EXPERIENCE_SCHEMA = "agentos.experience/v0"
ACCEPTED_STATUS = "accepted"
VALID_KINDS = {
    "decision",
    "procedure",
    "heuristic",
    "failure-pattern",
    "constraint",
    "benchmark-pattern",
}


class ExperienceContractError(ValueError):
    """Raised when an experience artifact violates the v0 contract."""


@dataclass(frozen=True)
class ExperienceQuery:
    project_id: str
    realm: str | None = None
    capabilities: tuple[str, ...] = ()
    executor: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class HydrationProjection:
    schema: str
    project_id: str
    active_goal: str
    experience_ids: tuple[str, ...]
    items: tuple[Mapping[str, Any], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "project_id": self.project_id,
            "active_goal": self.active_goal,
            "experience_ids": list(self.experience_ids),
            "items": [dict(item) for item in self.items],
            "digest": self.digest,
        }


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
        raise ExperienceContractError(f"{field} must be a list of non-empty strings")
    return tuple(value)


def validate_experience(artifact: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "experience_id",
        "project_id",
        "kind",
        "summary",
        "payload",
        "provenance",
        "authority",
        "validity",
    }
    missing = required.difference(artifact)
    if missing:
        raise ExperienceContractError(f"missing required fields: {sorted(missing)}")
    if artifact["schema"] != EXPERIENCE_SCHEMA:
        raise ExperienceContractError("unsupported experience schema")
    for field in ("experience_id", "project_id", "summary"):
        if not isinstance(artifact[field], str) or not artifact[field].strip():
            raise ExperienceContractError(f"{field} must be a non-empty string")
    if artifact["kind"] not in VALID_KINDS:
        raise ExperienceContractError("unsupported experience kind")
    if not isinstance(artifact["payload"], Mapping):
        raise ExperienceContractError("payload must be an object")

    provenance = artifact["provenance"]
    if not isinstance(provenance, Mapping):
        raise ExperienceContractError("provenance must be an object")
    sources = _string_list(provenance.get("sources"), "provenance.sources")
    if not sources:
        raise ExperienceContractError("provenance.sources must not be empty")
    _string_list(provenance.get("accepted_evidence", []), "provenance.accepted_evidence")

    authority = artifact["authority"]
    if not isinstance(authority, Mapping) or authority.get("status") not in {
        "candidate",
        "accepted",
        "deprecated",
        "revoked",
    }:
        raise ExperienceContractError("authority.status is invalid")
    _string_list(authority.get("supersedes", []), "authority.supersedes")
    _string_list(authority.get("superseded_by", []), "authority.superseded_by")

    validity = artifact["validity"]
    if not isinstance(validity, Mapping):
        raise ExperienceContractError("validity must be an object")
    _string_list(validity.get("conditions", []), "validity.conditions")
    _string_list(validity.get("invalidated_by", []), "validity.invalidated_by")
    _string_list(artifact.get("realm_scope", []), "realm_scope")
    _string_list(artifact.get("capability_scope", []), "capability_scope")
    _string_list(artifact.get("executor_scope", []), "executor_scope")


def _scope_matches(scope: Sequence[str], value: str | None) -> bool:
    return not scope or value is None or value in scope or "*" in scope


def _capability_score(scope: Sequence[str], requested: set[str]) -> int:
    if not scope:
        return 0
    if "*" in scope:
        return 1
    return len(set(scope).intersection(requested))


def discover_experience(
    artifacts: Iterable[Mapping[str, Any]], query: ExperienceQuery
) -> list[Mapping[str, Any]]:
    """Return accepted, in-scope experience ranked deterministically.

    Discovery is intentionally authority-neutral: it only returns knowledge
    artifacts. Mutation/execution authority must be resolved elsewhere.
    """
    if not query.project_id:
        raise ExperienceContractError("query.project_id must be non-empty")
    if query.limit < 1:
        raise ExperienceContractError("query.limit must be positive")

    requested_caps = set(query.capabilities)
    ranked: list[tuple[tuple[int, int, int, str], Mapping[str, Any]]] = []
    for artifact in artifacts:
        validate_experience(artifact)
        if artifact["project_id"] != query.project_id:
            continue
        if artifact["authority"]["status"] != ACCEPTED_STATUS:
            continue
        if artifact["authority"].get("superseded_by"):
            continue
        if artifact["validity"].get("invalidated_by"):
            continue

        realms = tuple(artifact.get("realm_scope", []))
        executors = tuple(artifact.get("executor_scope", []))
        capabilities = tuple(artifact.get("capability_scope", []))
        if not _scope_matches(realms, query.realm):
            continue
        if not _scope_matches(executors, query.executor):
            continue
        if capabilities and requested_caps and not ({"*"} | requested_caps).intersection(capabilities):
            continue

        # Prefer exact executor/realm scope and capability overlap; tie-break by ID.
        score = (
            1 if query.executor and query.executor in executors else 0,
            1 if query.realm and query.realm in realms else 0,
            _capability_score(capabilities, requested_caps),
            artifact["experience_id"],
        )
        ranked.append((score, artifact))

    ranked.sort(key=lambda item: (-item[0][0], -item[0][1], -item[0][2], item[0][3]))
    return [artifact for _, artifact in ranked[: query.limit]]


def hydrate_experience(
    *, project_id: str, active_goal: str, artifacts: Sequence[Mapping[str, Any]]
) -> HydrationProjection:
    """Create a bounded executor-neutral projection from discovered experience."""
    if not project_id or not active_goal:
        raise ExperienceContractError("project_id and active_goal must be non-empty")

    items: list[Mapping[str, Any]] = []
    ids: list[str] = []
    for artifact in artifacts:
        validate_experience(artifact)
        if artifact["project_id"] != project_id:
            raise ExperienceContractError("hydration artifact project mismatch")
        if artifact["authority"]["status"] != ACCEPTED_STATUS:
            raise ExperienceContractError("hydration accepts only accepted experience")
        ids.append(artifact["experience_id"])
        items.append(
            {
                "experience_id": artifact["experience_id"],
                "kind": artifact["kind"],
                "summary": artifact["summary"],
                "payload": artifact["payload"],
                "provenance": {
                    "sources": list(artifact["provenance"]["sources"]),
                    "accepted_evidence": list(artifact["provenance"].get("accepted_evidence", [])),
                },
            }
        )

    canonical = {
        "schema": "agentos.experience-hydration/v0",
        "project_id": project_id,
        "active_goal": active_goal,
        "experience_ids": ids,
        "items": items,
    }
    digest = sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return HydrationProjection(
        schema="agentos.experience-hydration/v0",
        project_id=project_id,
        active_goal=active_goal,
        experience_ids=tuple(ids),
        items=tuple(items),
        digest=digest,
    )
