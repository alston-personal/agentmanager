from __future__ import annotations

import json
import os
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


def resolve_project_identity(
    query: str,
    *,
    governance_path: str | Path | None = None,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve a project without guessing from application data or source code.

    Canonical project entities in Governance Directory are preferred. Exact
    project IDs may fall back to an existing AGENT_DATA_ROOT/projects directory
    so already-registered projects remain addressable while the Governance
    Directory is being populated. Aliases are *never* inferred from folder
    names, product identity registries, Git repositories, or free text.
    """
    needle = _normalize(query)
    if not needle:
        raise ValueError("project query is required")

    gov_path = Path(governance_path) if governance_path is not None else REGISTRY_PATH
    matches: list[tuple[str, dict[str, Any]]] = []
    for entity in list_entities("project", path=gov_path):
        if entity.get("state") in INACTIVE_PROJECT_STATES:
            continue
        project_id = _project_slug(entity)
        candidates = {
            "id": project_id,
            "entity_id": str(entity.get("id") or ""),
            "name": str(entity.get("name") or ""),
        }
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
        return {
            "id": project_id,
            "name": str(entity.get("name") or project_id),
            "aliases": _project_aliases(entity),
            "resolution": "alias" if matched_by == "alias" else "exact",
            "matched_by": matched_by,
            "identity_source": "governance-directory",
            "governance_entity_id": entity.get("id"),
            "governance_state": entity.get("state"),
        }

    # Conservative migration fallback: exact canonical folder ID only. This is
    # not alias discovery and does not inspect STATUS.md or app-owned registries.
    root = _data_root(data_root)
    projects_dir = root / "projects"
    exact_dir = projects_dir / str(query).strip()
    if exact_dir.is_dir() and _normalize(exact_dir.name) == needle:
        return {
            "id": exact_dir.name,
            "name": exact_dir.name,
            "aliases": [],
            "resolution": "exact",
            "matched_by": "project_id",
            "identity_source": "project-data-exact-id-fallback",
            "governance_entity_id": None,
            "governance_state": None,
        }

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
        return {
            "protocol": raw.get("protocol"),
            "recommended_action": raw.get("recommended_action"),
            "canonical_ir": None,
        }
    return {
        "protocol": raw.get("protocol"),
        "recommended_action": raw.get("recommended_action"),
        "canonical_ir": canonical_ir,
        "ir_id": canonical_ir.get("ir_id"),
        "parent_ir_id": canonical_ir.get("parent_ir_id"),
        "goal": canonical_ir.get("goal"),
        "constraints": canonical_ir.get("constraints") or [],
        "decisions": canonical_ir.get("decisions") or [],
        "pending_tasks": canonical_ir.get("pending_tasks") or [],
        "continuation": canonical_ir.get("continuation") or {},
        "capability": canonical_ir.get("capability"),
    }


def resolve_continuation(
    project_query: str,
    *,
    governance_path: str | Path | None = None,
    data_root: str | Path | None = None,
    node_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose a read-only canonical continuation envelope for ONE clients."""
    root = _data_root(data_root)
    project = resolve_project_identity(
        project_query,
        governance_path=governance_path,
        data_root=root,
    )
    project_dir = root / "projects" / project["id"]

    execution_head = _read_json(project_dir / "execution-head.json")
    if execution_head is not None and execution_head.get("schema") != "agentos.execution-head/v1":
        raise ValueError("unsupported execution-head schema")

    raw_continuation = _read_json(project_dir / "continuity" / "latest.json")
    continuation = _continuation_projection(raw_continuation)
    active_goal = continuation.get("goal") if continuation else None
    recommended_action = continuation.get("recommended_action") if continuation else None

    return {
        "schema": "agentos.resolve/v1",
        "intent": "continue",
        "project": project,
        "active_goal": active_goal,
        "execution_head": execution_head,
        "continuation": continuation,
        "node_context": node_context,
        "next_action": recommended_action,
        "availability": {
            "project_identity": True,
            "continuation": continuation is not None,
            "execution_head": execution_head is not None,
            "node_context": node_context is not None,
            "last_receipt": False,
        },
        "provenance": {
            "project_identity": project["identity_source"],
            "continuation": "project/continuity/latest.json" if continuation is not None else None,
            "execution_head": "project/execution-head.json" if execution_head is not None else None,
            "last_receipt": "not-yet-project-indexed",
        },
    }
