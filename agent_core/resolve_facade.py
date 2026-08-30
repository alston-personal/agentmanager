from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.governance_directory import REGISTRY_PATH, list_entities


INACTIVE_PROJECT_STATES = {"retired", "superseded", "stale"}


def _data_root(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def _normalize(value: str) -> str:
    return str(value or "").strip().casefold()


def _project_slug(entity: dict[str, Any]) -> str:
    entity_id = str(entity.get("id") or "")
    if entity_id.startswith("project://"):
        return entity_id[len("project://") :]
    return entity_id


def _project_aliases(entity: dict[str, Any]) -> list[str]:
    metadata = entity.get("metadata") or {}
    raw = metadata.get("aliases") or []
    if isinstance(raw, str):
        raw = [raw]
    aliases = []
    for item in raw:
        value = str(item or "").strip()
        if value and value not in aliases:
            aliases.append(value)
    return aliases


def _project_authority(entity: dict[str, Any]) -> dict[str, Any]:
    implementation = entity.get("implementation") or {}
    metadata = entity.get("metadata") or {}
    source = implementation.get("source") if isinstance(implementation.get("source"), dict) else {}
    if not source:
        source = {
            "repo": implementation.get("repo"),
            "branch": implementation.get("branch"),
            "canonical_path": implementation.get("canonical_path"),
            "node": implementation.get("node"),
        }
    else:
        source = dict(source)
    runtime = implementation.get("runtime") if isinstance(implementation.get("runtime"), dict) else {}
    deployment = implementation.get("deployment") if isinstance(implementation.get("deployment"), dict) else {}
    surfaces = metadata.get("surfaces") if isinstance(metadata.get("surfaces"), list) else []
    state = metadata.get("state") if isinstance(metadata.get("state"), dict) else {}
    required = {
        "canonical_repo": bool(source.get("repo")),
        "canonical_branch": bool(source.get("branch")),
        "canonical_checkout": bool(source.get("canonical_path")),
        "canonical_node": bool(source.get("node")),
        "state_authority": bool(state.get("document") or state.get("checkpoint") or state.get("continuity")),
    }
    complete = all(required.values())
    return {
        "source": source,
        "runtime": dict(runtime),
        "deployment": dict(deployment),
        "surfaces": list(surfaces),
        "state": dict(state),
        "integrity": {
            "required": required,
            "complete": complete,
            "mutation_allowed": complete,
            "reason": None if complete else "project resolution incomplete; source/path/state authority must be canonical before mutation",
        },
    }


def _resolution_receipt(query: str, project: dict[str, Any]) -> dict[str, Any]:
    integrity = project.get("integrity") or {}
    source = project.get("source") or {}
    state = project.get("state") or {}
    confidence = {
        "identity": 1.0 if project.get("identity_source") == "governance-directory" else 0.6,
        "source": 1.0 if integrity.get("required", {}).get("canonical_repo") else 0.0,
        "runtime": 1.0 if integrity.get("required", {}).get("canonical_node") else 0.0,
    }
    return {
        "schema": "agentos.project-resolution/v1",
        "query": query,
        "resolved": {
            "project_id": project.get("id"),
            "aliases": project.get("aliases") or [],
            "repo": source.get("repo"),
            "branch": source.get("branch"),
            "canonical_path": source.get("canonical_path"),
            "node": source.get("node"),
            "checkpoint": state.get("checkpoint") or state.get("document") or state.get("continuity"),
        },
        "confidence": confidence,
        "integrity": integrity,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def resolve_project_identity(query: str, *, governance_path: str | Path | None = None, data_root: str | Path | None = None) -> dict[str, Any]:
    needle = _normalize(query)
    if not needle:
        raise ValueError("project query is required")
    gov_path = Path(governance_path) if governance_path is not None else REGISTRY_PATH
    matches: list[tuple[str, dict[str, Any]]] = []
    for entity in list_entities("project", path=gov_path):
        if entity.get("state") in INACTIVE_PROJECT_STATES:
            continue
        project_id = _project_slug(entity)
        candidates = {"id": project_id, "entity_id": str(entity.get("id") or ""), "name": str(entity.get("name") or "")}
        aliases = _project_aliases(entity)
        matched_by = None
        for kind, value in candidates.items():
            if _normalize(value) == needle:
                matched_by = kind
                break
        if matched_by is None and any(_normalize(alias) == needle for alias in aliases):
            matched_by = "alias"
        if matched_by:
            matches.append((matched_by, entity))
    if len(matches) > 1:
        ids = sorted(_project_slug(entity) for _, entity in matches)
        raise ValueError(f"ambiguous project identity: {query!r} -> {ids}")
    if matches:
        matched_by, entity = matches[0]
        project_id = _project_slug(entity)
        project = {
            "id": project_id,
            "name": str(entity.get("name") or project_id),
            "aliases": _project_aliases(entity),
            "resolution": "alias" if matched_by == "alias" else "exact",
            "matched_by": matched_by,
            "identity_source": "governance-directory",
            "governance_entity_id": entity.get("id"),
            "governance_state": entity.get("state"),
        }
        project.update(_project_authority(entity))
        project["resolution_receipt"] = _resolution_receipt(query, project)
        return project
    root = _data_root(data_root)
    exact_dir = root / "projects" / str(query).strip()
    if exact_dir.is_dir() and _normalize(exact_dir.name) == needle:
        project = {
            "id": exact_dir.name,
            "name": exact_dir.name,
            "aliases": [],
            "resolution": "exact",
            "matched_by": "project_id",
            "identity_source": "project-data-exact-id-fallback",
            "governance_entity_id": None,
            "governance_state": None,
            "source": {}, "runtime": {}, "deployment": {}, "surfaces": [], "state": {},
            "integrity": {
                "required": {"canonical_repo": False, "canonical_branch": False, "canonical_checkout": False, "canonical_node": False, "state_authority": False},
                "complete": False,
                "mutation_allowed": False,
                "reason": "exact project-data directory fallback proves identity only; canonical source/path/state authority unresolved",
            },
        }
        project["resolution_receipt"] = _resolution_receipt(query, project)
        return project
    raise KeyError(f"project identity unresolved: {query}")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _continuation_projection(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    canonical_ir = raw.get("canonical_ir") if isinstance(raw.get("canonical_ir"), dict) else None
    if canonical_ir is None and raw.get("schema_version") == "agentos.ir/v1":
        canonical_ir = raw
    if canonical_ir is None:
        return {"protocol": raw.get("protocol"), "recommended_action": raw.get("recommended_action"), "canonical_ir": None}
    return {
        "protocol": raw.get("protocol"), "recommended_action": raw.get("recommended_action"), "canonical_ir": canonical_ir,
        "ir_id": canonical_ir.get("ir_id"), "parent_ir_id": canonical_ir.get("parent_ir_id"), "goal": canonical_ir.get("goal"),
        "constraints": canonical_ir.get("constraints") or [], "decisions": canonical_ir.get("decisions") or [],
        "pending_tasks": canonical_ir.get("pending_tasks") or [], "continuation": canonical_ir.get("continuation") or {}, "capability": canonical_ir.get("capability"),
    }


def resolve_continuation(project_query: str, *, governance_path: str | Path | None = None, data_root: str | Path | None = None, node_context: dict[str, Any] | None = None) -> dict[str, Any]:
    root = _data_root(data_root)
    project = resolve_project_identity(project_query, governance_path=governance_path, data_root=root)
    project_dir = root / "projects" / project["id"]
    execution_head = _read_json(project_dir / "execution-head.json")
    if execution_head is not None and execution_head.get("schema") != "agentos.execution-head/v1":
        raise ValueError("unsupported execution-head schema")
    raw_continuation = _read_json(project_dir / "continuity" / "latest.json")
    continuation = _continuation_projection(raw_continuation)
    active_goal = continuation.get("goal") if continuation else None
    recommended_action = continuation.get("recommended_action") if continuation else None
    return {
        "schema": "agentos.resolve/v1", "intent": "continue", "project": project, "project_resolution": project.get("resolution_receipt"),
        "mutation_allowed": bool(project.get("integrity", {}).get("mutation_allowed")), "active_goal": active_goal,
        "execution_head": execution_head, "continuation": continuation, "node_context": node_context, "next_action": recommended_action,
        "availability": {"project_identity": True, "project_integrity": bool(project.get("integrity", {}).get("complete")), "continuation": continuation is not None, "execution_head": execution_head is not None, "node_context": node_context is not None, "last_receipt": False},
        "provenance": {"project_identity": project["identity_source"], "project_resolution": "governance-directory" if project.get("governance_entity_id") else "project-data-exact-id-fallback", "continuation": "project/continuity/latest.json" if continuation is not None else None, "execution_head": "project/execution-head.json" if execution_head is not None else None, "last_receipt": "not-yet-project-indexed"},
    }
