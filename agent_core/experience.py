"""Governed ONE Experience IR discovery and hydration primitives.

Experience is a governed projection over canonical state/evidence, not a fourth
source of truth. The semantic payload is machine-readable Experience IR. Human
summaries are optional display metadata and are never authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping, Sequence


EXPERIENCE_SCHEMA = "agentos.experience/v1"
EXPERIENCE_IR_SCHEMA = "agentos.experience-ir/v1"
EXTRACTION_SCHEMA = "agentos.experience-extraction/v1"
HYDRATION_SCHEMA = "agentos.experience-hydration/v1"
ACCEPTED_STATUS = "accepted"

VALID_KINDS = {
    "decision",
    "procedure",
    "heuristic",
    "failure-pattern",
    "constraint",
    "benchmark-pattern",
}
VALID_IR_OPS = {
    "assert",
    "require",
    "forbid",
    "prefer",
    "avoid",
    "invoke",
    "match",
    "set",
}
VALID_VALUE_TYPES = {"symbol", "string", "number", "boolean", "null", "list", "object"}
_SENSITIVE_KEYS = {
    "token",
    "node_token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "claim_secret",
    "client_secret",
}


class ExperienceContractError(ValueError):
    """Raised when an Experience artifact violates the contract."""


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


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _string_list(value: Any, field: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None:
        if required:
            raise ExperienceContractError(f"{field} must not be empty")
        return ()
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise ExperienceContractError(f"{field} must be a list of non-empty strings")
    result = tuple(v.strip() for v in value)
    if required and not result:
        raise ExperienceContractError(f"{field} must not be empty")
    return result


def _contains_sensitive(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().casefold() in _SENSITIVE_KEYS:
                return True
            if _contains_sensitive(child):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive(child) for child in value)
    return False


def _validate_typed_value(value: Any, field: str) -> None:
    if not isinstance(value, Mapping):
        raise ExperienceContractError(f"{field} must be an object")
    value_type = value.get("type")
    if value_type not in VALID_VALUE_TYPES:
        raise ExperienceContractError(f"{field}.type is unsupported")
    if value_type == "null":
        if value.get("value") is not None:
            raise ExperienceContractError(f"{field}.value must be null")
        return
    if "value" not in value:
        raise ExperienceContractError(f"{field}.value is required")
    raw = value["value"]
    if value_type in {"symbol", "string"} and (not isinstance(raw, str) or not raw.strip()):
        raise ExperienceContractError(f"{field}.value must be a non-empty string")
    if value_type == "number" and (not isinstance(raw, (int, float)) or isinstance(raw, bool)):
        raise ExperienceContractError(f"{field}.value must be a number")
    if value_type == "boolean" and not isinstance(raw, bool):
        raise ExperienceContractError(f"{field}.value must be boolean")
    if value_type == "list" and not isinstance(raw, list):
        raise ExperienceContractError(f"{field}.value must be a list")
    if value_type == "object" and not isinstance(raw, Mapping):
        raise ExperienceContractError(f"{field}.value must be an object")


def validate_experience_ir(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ExperienceContractError("ir must be an object")
    if value.get("schema") != EXPERIENCE_IR_SCHEMA:
        raise ExperienceContractError("unsupported experience IR schema")
    nodes = value.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ExperienceContractError("ir.nodes must be a non-empty list")
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        field = f"ir.nodes[{index}]"
        if not isinstance(node, Mapping):
            raise ExperienceContractError(f"{field} must be an object")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise ExperienceContractError(f"{field}.id must be a non-empty string")
        if node_id in seen:
            raise ExperienceContractError(f"duplicate IR node id: {node_id}")
        seen.add(node_id)
        if node.get("op") not in VALID_IR_OPS:
            raise ExperienceContractError(f"{field}.op is unsupported")
        predicate = node.get("predicate")
        if not isinstance(predicate, str) or not predicate.strip():
            raise ExperienceContractError(f"{field}.predicate must be a non-empty string")
        arguments = node.get("arguments", [])
        if not isinstance(arguments, list):
            raise ExperienceContractError(f"{field}.arguments must be a list")
        for arg_index, argument in enumerate(arguments):
            _validate_typed_value(argument, f"{field}.arguments[{arg_index}]")
        if "value" in node:
            _validate_typed_value(node["value"], f"{field}.value")

    entrypoints = _string_list(value.get("entrypoints"), "ir.entrypoints", required=True)
    missing = [item for item in entrypoints if item not in seen]
    if missing:
        raise ExperienceContractError(f"ir.entrypoints reference missing nodes: {missing}")
    _string_list(
        value.get("expected_behavior_dimensions"),
        "ir.expected_behavior_dimensions",
        required=True,
    )
    if _contains_sensitive(value):
        raise ExperienceContractError("experience IR contains a sensitive credential field")


def validate_experience(artifact: Mapping[str, Any]) -> None:
    required = {
        "schema",
        "experience_id",
        "project_id",
        "kind",
        "ir",
        "provenance",
        "authority",
        "validity",
    }
    missing = required.difference(artifact)
    if missing:
        raise ExperienceContractError(f"missing required fields: {sorted(missing)}")
    if artifact["schema"] != EXPERIENCE_SCHEMA:
        raise ExperienceContractError("unsupported experience schema")
    for field in ("experience_id", "project_id"):
        if not isinstance(artifact[field], str) or not artifact[field].strip():
            raise ExperienceContractError(f"{field} must be a non-empty string")
    if artifact["kind"] not in VALID_KINDS:
        raise ExperienceContractError("unsupported experience kind")

    validate_experience_ir(artifact["ir"])

    display = artifact.get("display", {})
    if not isinstance(display, Mapping):
        raise ExperienceContractError("display must be an object")
    summary = display.get("summary")
    if summary is not None and (not isinstance(summary, str) or not summary.strip()):
        raise ExperienceContractError("display.summary must be a non-empty string when present")

    provenance = artifact["provenance"]
    if not isinstance(provenance, Mapping):
        raise ExperienceContractError("provenance must be an object")
    _string_list(provenance.get("sources"), "provenance.sources", required=True)
    _string_list(provenance.get("accepted_evidence", []), "provenance.accepted_evidence")
    extraction_id = provenance.get("extraction_id")
    if extraction_id is not None and (not isinstance(extraction_id, str) or not extraction_id.strip()):
        raise ExperienceContractError("provenance.extraction_id must be a non-empty string when present")

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

    if _contains_sensitive(artifact):
        raise ExperienceContractError("experience artifact contains a sensitive credential field")


def validate_extraction_proposal(proposal: Mapping[str, Any]) -> None:
    if not isinstance(proposal, Mapping):
        raise ExperienceContractError("extraction proposal must be an object")
    if proposal.get("schema") != EXTRACTION_SCHEMA:
        raise ExperienceContractError("unsupported extraction proposal schema")
    for field in ("extraction_id", "project_id"):
        if not isinstance(proposal.get(field), str) or not str(proposal[field]).strip():
            raise ExperienceContractError(f"{field} must be a non-empty string")
    origin = proposal.get("origin")
    if not isinstance(origin, Mapping):
        raise ExperienceContractError("origin must be an object")
    if not any(str(origin.get(field) or "").strip() for field in ("node_id", "surface", "executor", "backend")):
        raise ExperienceContractError("origin must identify at least one trustworthy execution surface field")
    sources = _string_list(proposal.get("sources"), "sources", required=True)
    if not sources:
        raise ExperienceContractError("sources must not be empty")
    abstraction = proposal.get("abstraction")
    if not isinstance(abstraction, Mapping):
        raise ExperienceContractError("abstraction must be an object")
    _string_list(abstraction.get("generalized_from"), "abstraction.generalized_from", required=True)
    _string_list(abstraction.get("excluded", []), "abstraction.excluded")
    candidate = proposal.get("candidate")
    if not isinstance(candidate, Mapping):
        raise ExperienceContractError("candidate must be an object")
    validate_experience(candidate)
    if candidate["authority"]["status"] != "candidate":
        raise ExperienceContractError("extraction proposal candidate must not self-authorize acceptance")
    if candidate["project_id"] != proposal["project_id"]:
        raise ExperienceContractError("extraction proposal project mismatch")
    if _contains_sensitive(proposal):
        raise ExperienceContractError("extraction proposal contains a sensitive credential field")


def experience_semantic_digest(artifact: Mapping[str, Any]) -> str:
    """Hash semantic Experience content, excluding optional human display text."""
    validate_experience(artifact)
    semantic = {
        "schema": artifact["schema"],
        "experience_id": artifact["experience_id"],
        "project_id": artifact["project_id"],
        "kind": artifact["kind"],
        "realm_scope": list(artifact.get("realm_scope", [])),
        "capability_scope": list(artifact.get("capability_scope", [])),
        "executor_scope": list(artifact.get("executor_scope", [])),
        "ir": artifact["ir"],
        "validity": artifact["validity"],
    }
    return "sha256:" + sha256(_canonical(semantic)).hexdigest()


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
    """Return accepted, current, in-scope Experience ranked deterministically."""
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
    """Create an executor-neutral semantic projection from accepted Experience."""
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
        experience_id = artifact["experience_id"]
        ids.append(experience_id)
        items.append(
            {
                "experience_id": experience_id,
                "kind": artifact["kind"],
                "semantic_digest": experience_semantic_digest(artifact),
                "ir": artifact["ir"],
                "expected_behavior_dimensions": list(
                    artifact["ir"]["expected_behavior_dimensions"]
                ),
                "provenance": {
                    "sources": list(artifact["provenance"]["sources"]),
                    "accepted_evidence": list(
                        artifact["provenance"].get("accepted_evidence", [])
                    ),
                    **(
                        {"extraction_id": artifact["provenance"]["extraction_id"]}
                        if artifact["provenance"].get("extraction_id")
                        else {}
                    ),
                },
            }
        )

    canonical = {
        "schema": HYDRATION_SCHEMA,
        "project_id": project_id,
        "active_goal": active_goal,
        "experience_ids": ids,
        "items": items,
    }
    digest = "sha256:" + sha256(_canonical(canonical)).hexdigest()
    return HydrationProjection(
        schema=HYDRATION_SCHEMA,
        project_id=project_id,
        active_goal=active_goal,
        experience_ids=tuple(ids),
        items=tuple(items),
        digest=digest,
    )
