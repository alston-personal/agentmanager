"""Generic discovery adapter for reusable AgentOS capability manifests.

Only manifests that explicitly opt in via discovery.governance_directory are
mirrored. This keeps capability registration data-driven and avoids adding a
new hard-coded Governance Directory entity for every reusable capability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .governance_directory import PROJECT_ROOT, REGISTRY_PATH, GovernanceEntity, upsert


CAPABILITY_ROOT = PROJECT_ROOT / "capabilities"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"capability manifest must be an object: {path}")
    if value.get("schema") != "agentos.capability-manifest/v1":
        raise ValueError(f"unsupported capability manifest schema: {path}")
    return value


def sync_discoverable_capability_manifests(
    *,
    capability_root: Path = CAPABILITY_ROOT,
    directory_path: Path = REGISTRY_PATH,
) -> list[GovernanceEntity]:
    mirrored: list[GovernanceEntity] = []
    if not capability_root.exists():
        return mirrored

    for path in sorted(capability_root.glob("*/capability-manifest.json")):
        data = _load(path)
        discovery = data.get("discovery") or {}
        if not isinstance(discovery, dict) or not discovery.get("governance_directory"):
            continue

        capability_id = str(data.get("capability_id") or "").strip()
        provider_id = str(discovery.get("provider_id") or "").strip()
        if not capability_id:
            raise ValueError(f"capability_id is required: {path}")
        if not provider_id.startswith("service://"):
            raise ValueError(f"discovery.provider_id must be service://: {path}")

        lifecycle = str(data.get("lifecycle") or "declared")
        state = "implemented" if lifecycle in {"implemented", "stable"} else "declared"
        invocation = data.get("invocation") if isinstance(data.get("invocation"), dict) else {}

        entity = GovernanceEntity(
            id=provider_id,
            kind="service",
            name=str(data.get("display_name") or capability_id),
            owns=[],
            provides=[f"capability://{capability_id}"],
            implementation={
                "repo": "alston-personal/agentmanager",
                "manifest": str(path.relative_to(PROJECT_ROOT)),
                "invocation": invocation,
            },
            authority={
                "exclusive": False,
                "canonical_capability_contract": True,
                "reuse_before_build": bool(discovery.get("reuse_before_build", True)),
            },
            state=state,
            owner="role://governance.keeper",
            metadata={
                "version": data.get("version"),
                "semantic_owner": data.get("semantic_owner"),
                "contract": data.get("contract") or {},
                "policy": data.get("policy") or {},
            },
        )
        upsert(entity, path=directory_path)
        mirrored.append(entity)
    return mirrored
