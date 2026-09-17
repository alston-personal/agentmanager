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
        value = sanitize_for_persistence(raw.get("value"))
        entry = sanitize_for_persistence(
            {
                "fact_key": fact_key,
                "value": value,
                "scope": str(raw.get("scope") or project_id),
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


def known_facts(project_id: str, *, data_root: str | Path | None = None) -> dict[str, KnownFact]:
    document = load_project_knowledge(project_id, data_root=data_root)
    result: dict[str, KnownFact] = {}
    for key, raw in document.get("facts", {}).items():
        if not isinstance(raw, dict):
            continue
        result[key] = KnownFact(
            fact_key=key,
            value=raw.get("value"),
            scope=str(raw.get("scope") or project_id),
            depth=str(raw.get("depth") or "summary"),
            evidence_strength=str(raw.get("evidence_strength") or "documented"),
            freshness=str(raw.get("freshness") or "fresh"),
            conflicting=bool(raw.get("conflicting", False)),
            source=raw.get("source"),
            verified_at=raw.get("verified_at"),
        )
    return result
