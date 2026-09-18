"""Adapter from canonical Studio release governance into the runtime directory.

The YAML file remains the source of truth for Studio release capability semantics.
This module mirrors those contracts into the Governance Directory so generic
capability resolution can discover them without learning Studio-specific formats.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

from .governance_directory import (
    PROJECT_ROOT,
    REGISTRY_PATH,
    GovernanceEntity,
    upsert,
)


STUDIO_CAPABILITY_REGISTRY = (
    PROJECT_ROOT / ".agent" / "governance" / "studio_release_capabilities.yaml"
)
_ALLOWED_STATES = {
    "declared",
    "implemented",
    "deployed",
    "observed",
    "verified",
    "stale",
    "drifted",
    "superseded",
    "retired",
}


def _load(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to sync Studio capability governance")
    if not path.exists():
        raise FileNotFoundError(path)
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def sync_studio_release_capabilities(
    *,
    source_path: Path = STUDIO_CAPABILITY_REGISTRY,
    directory_path: Path = REGISTRY_PATH,
) -> list[GovernanceEntity]:
    """Mirror canonical Studio release providers into the Governance Directory."""

    data = _load(source_path)
    mirrored: list[GovernanceEntity] = []
    for key, raw in (data.get("capabilities") or {}).items():
        if not isinstance(raw, dict):
            continue
        provider_id = str(raw.get("provider_id") or "").strip()
        capability_uri = str(raw.get("capability_uri") or "").strip()
        if not provider_id or not capability_uri:
            raise ValueError(
                f"Studio capability {key} is missing provider_id/capability_uri"
            )
        if not provider_id.startswith("service://"):
            raise ValueError(
                f"Studio capability provider must be service://: {provider_id}"
            )
        if not capability_uri.startswith("capability://"):
            raise ValueError(
                f"Studio capability URI must be capability://: {capability_uri}"
            )

        state = str(raw.get("state") or "implemented")
        if state not in _ALLOWED_STATES:
            raise ValueError(f"unsupported Studio capability state: {state}")

        entity = GovernanceEntity(
            id=provider_id,
            kind="service",
            name=str(key).replace("_", " ").title(),
            owns=[],
            provides=[capability_uri],
            implementation={
                "repo": "alston-personal/agentmanager",
                "canonical_registry": _display_path(source_path),
                "workflow": raw.get("canonical_workflow"),
                "regression_guard": raw.get("regression_guard"),
                "documentation": raw.get("documentation"),
                "source_repo": raw.get("source_repo"),
                "production_surface": raw.get("production_surface"),
            },
            authority={
                "exclusive": False,
                "canonical_capability_contract": True,
                "reuse_before_build": True,
            },
            state=state,
            owner="role://governance.keeper",
            metadata={
                "registry_key": key,
                "status": raw.get("status"),
                "scope": raw.get("scope"),
                "invariants": raw.get("invariants") or [],
                "consumers": raw.get("consumers") or {},
                "promotion_rule": raw.get("promotion_rule"),
            },
        )
        upsert(entity, path=directory_path)
        mirrored.append(entity)
    return mirrored
