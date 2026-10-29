from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from agent_core.discovery_reuse import KnownFact, sanitize_for_persistence


SCHEMA = "agentos.project-knowledge/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_root(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def knowledge_path(project_id: str, *, data_root: str | Path | None = None) -> Path:
    return _data_root(data_root) / "projects" / project_id / "knowledge" / "reusable-facts.json"


def load_project_knowledge(project_id: str, *, data_root: str | Path | None = None) -> dict[str, Any]:
    path = knowledge_path(project_id, data_root=data_root)
    if not path.is_file():
        return {"schema": SCHEMA, "project_id": project_id, "facts": {}, "updated_at": None}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ValueError(f"unsupported project knowledge document: {path}")
    facts = raw.get("facts")
    if not isinstance(facts, dict):
        raise ValueError(f"invalid project knowledge facts: {path}")
    return raw


def promote_reusable_facts(
    project_id: str,
    facts: Iterable[dict[str, Any]],
    *,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    """Persist sanitized reusable facts in the project data layer.

    This is deliberately separate from source/project identity authority. Facts
    can improve continuation without silently granting mutation authority.
    """
    document = load_project_knowledge(project_id, data_root=data_root)
    stored = document.setdefault("facts", {})
    promoted: list[dict[str, Any]] = []
    now = _utc_now()

    for raw in facts:
        fact_key = str(raw.get("fact_key") or "").strip()
        if not fact_key:
            raise ValueError("fact_key is required")
        entry = sanitize_for_persistence(
            {
                "fact_key": fact_key,
                "value": raw.get("value"),
                "scope": str(raw.get("scope") or f"project://{project_id}"),
                "depth": str(raw.get("depth") or "summary"),
                "source": raw.get("source"),
                "verified_at": raw.get("verified_at") or now,
                "freshness": str(raw.get("freshness") or "fresh"),
                "freshness_policy": raw.get("freshness_policy"),
                "evidence_strength": str(raw.get("evidence_strength") or "documented"),
                "sensitivity": str(raw.get("sensitivity") or "normal"),
                "supersedes": raw.get("supersedes"),
            }
        )
        stored[fact_key] = entry
        promoted.append({"fact_key": fact_key, "promoted": True, "destination": "project_knowledge"})

    document["updated_at"] = now
    path = knowledge_path(project_id, data_root=data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return {"project_id": project_id, "path": str(path), "promoted": promoted}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _resource_freshness(resource: dict[str, Any]) -> str:
    verification = resource.get("verification") if isinstance(resource.get("verification"), dict) else {}
    status = str(verification.get("status") or "unverified")
    verified = _parse_time(verification.get("last_verified_at"))
    ttl = int(verification.get("ttl_seconds", 86400) or 86400)
    if verified is None or status == "unverified":
        return "unverified"
    age = max(0, int((datetime.now(timezone.utc) - verified.astimezone(timezone.utc)).total_seconds()))
    if age > ttl:
        return "stale"
    return "fresh" if status == "verified" else status


def _resource_matches_project(resource: dict[str, Any], project_id: str) -> bool:
    labels = resource.get("labels") if isinstance(resource.get("labels"), dict) else {}
    declared = resource.get("declared") if isinstance(resource.get("declared"), dict) else {}
    candidates = {
        str(labels.get("project_id") or ""),
        str(labels.get("project") or ""),
        str(declared.get("project_id") or ""),
        str(declared.get("project") or ""),
    }
    return project_id in candidates


def _resource_registry_facts(project_id: str, *, data_root: str | Path | None = None) -> dict[str, KnownFact]:
    root = _data_root(data_root)
    path = root / "resources" / "registry.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    resources = raw.get("resources") if isinstance(raw, dict) else None
    if not isinstance(resources, dict):
        return {}

    scope = f"project://{project_id}"
    result: dict[str, KnownFact] = {}
    for resource_id, resource in resources.items():
        if not isinstance(resource, dict) or not _resource_matches_project(resource, project_id):
            continue
        declared = resource.get("declared") if isinstance(resource.get("declared"), dict) else {}
        observed = resource.get("observed") if isinstance(resource.get("observed"), dict) else {}
        freshness = _resource_freshness(resource)
        verified_at = (resource.get("verification") or {}).get("last_verified_at")

        recognized = {
            "runtime.service": declared.get("service") or declared.get("service_name"),
            "runtime.port": declared.get("port"),
            "runtime.repo_path": declared.get("repo_path"),
            "runtime.source_path": declared.get("source_path"),
            "runtime.dist_path": declared.get("dist_path"),
            "runtime.nginx_config": declared.get("nginx_config"),
        }
        git_state = observed.get("git") if isinstance(observed.get("git"), dict) else {}
        recognized.update(
            {
                "runtime.git.remote": git_state.get("origin"),
                "runtime.git.branch": git_state.get("branch"),
                "runtime.git.commit": git_state.get("commit"),
            }
        )

        for fact_key, value in recognized.items():
            if value in (None, ""):
                continue
            result[fact_key] = KnownFact(
                fact_key=fact_key,
                value=sanitize_for_persistence(value),
                scope=scope,
                depth="runtime",
                evidence_strength="verified" if freshness == "fresh" else "observed",
                freshness=freshness,
                source=f"resource-registry:{resource_id}",
                verified_at=verified_at,
            )
    return result


def known_facts(project_id: str, *, data_root: str | Path | None = None) -> dict[str, KnownFact]:
    # Runtime/resource registry is hydrated before broad discovery. Persisted
    # project knowledge then overlays it because explicit project promotion is
    # the more specific project-local representation.
    result = _resource_registry_facts(project_id, data_root=data_root)
    document = load_project_knowledge(project_id, data_root=data_root)
    for key, raw in document.get("facts", {}).items():
        if not isinstance(raw, dict):
            continue
        result[key] = KnownFact(
            fact_key=key,
            value=sanitize_for_persistence(raw.get("value")),
            scope=str(raw.get("scope") or f"project://{project_id}"),
            depth=str(raw.get("depth") or "summary"),
            evidence_strength=str(raw.get("evidence_strength") or "documented"),
            freshness=str(raw.get("freshness") or "fresh"),
            conflicting=bool(raw.get("conflicting", False)),
            source=raw.get("source"),
            verified_at=raw.get("verified_at"),
        )
    return result
