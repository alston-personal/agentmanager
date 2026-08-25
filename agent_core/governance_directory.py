from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

PROJECT_ROOT = Path(os.environ.get("AGENTMANAGER_ROOT", Path(__file__).resolve().parents[1]))
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
REGISTRY_PATH = DATA_ROOT / "governance" / "directory.json"
ROLE_REGISTRY_PATH = PROJECT_ROOT / ".agent" / "roles" / "registry.yaml"

VALID_KINDS = {"role", "capability", "manager", "service", "resource", "policy", "spec", "project", "node"}
VALID_STATES = {"declared", "implemented", "deployed", "observed", "verified", "stale", "drifted", "superseded", "retired"}


@dataclass
class GovernanceEntity:
    id: str
    kind: str
    name: str
    owns: list[str]
    provides: list[str]
    implementation: dict
    authority: dict
    state: str = "declared"
    owner: str | None = None
    supersedes: list[str] | None = None
    last_verified_at: str | None = None
    metadata: dict | None = None

    def validate(self) -> None:
        if self.kind not in VALID_KINDS:
            raise ValueError(f"invalid kind: {self.kind}")
        if self.state not in VALID_STATES:
            raise ValueError(f"invalid state: {self.state}")
        prefix = f"{self.kind}://"
        if not self.id.startswith(prefix):
            raise ValueError(f"id must start with {prefix}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_directory(path: Path = REGISTRY_PATH) -> dict:
    if not path.exists():
        return {"schema_version": "0.1", "updated_at": None, "entities": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("schema_version", "0.1")
    data.setdefault("entities", {})
    return data


def save_directory(data: dict, path: Path = REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def register(entity: GovernanceEntity, *, replace: bool = False, path: Path = REGISTRY_PATH) -> GovernanceEntity:
    entity.validate()
    data = load_directory(path)
    current = data["entities"].get(entity.id)
    if current and not replace:
        raise ValueError(f"entity already exists: {entity.id}")

    if entity.authority.get("exclusive"):
        claimed = set(entity.owns)
        for other_id, other in data["entities"].items():
            if other_id == entity.id or other.get("state") in {"retired", "superseded"}:
                continue
            if other.get("authority", {}).get("exclusive") and claimed.intersection(other.get("owns", [])):
                overlap = sorted(claimed.intersection(other.get("owns", [])))
                raise ValueError(f"exclusive ownership conflict with {other_id}: {overlap}")

    data["entities"][entity.id] = asdict(entity)
    save_directory(data, path)
    return entity


def upsert(entity: GovernanceEntity, *, path: Path = REGISTRY_PATH) -> GovernanceEntity:
    """Replace an entity while preserving runtime verification metadata when compatible."""
    entity.validate()
    data = load_directory(path)
    current = data["entities"].get(entity.id)
    if current:
        entity.last_verified_at = current.get("last_verified_at")
        if current.get("state") in {"verified", "observed", "deployed"} and entity.state not in {"retired", "superseded", "stale"}:
            entity.state = current["state"]
        merged_meta = dict(entity.metadata or {})
        merged_meta.update(current.get("metadata") or {})
        entity.metadata = merged_meta or None
    data["entities"][entity.id] = asdict(entity)
    save_directory(data, path)
    return entity


def get(entity_id: str, path: Path = REGISTRY_PATH) -> dict | None:
    return load_directory(path)["entities"].get(entity_id)


def list_entities(kind: str | None = None, path: Path = REGISTRY_PATH) -> list[dict]:
    values = list(load_directory(path)["entities"].values())
    if kind:
        values = [v for v in values if v.get("kind") == kind]
    return sorted(values, key=lambda x: x["id"])


def resolve(capability: str, path: Path = REGISTRY_PATH) -> list[dict]:
    """Resolve active owners/providers of a capability; exclusive owners sort first."""
    out = []
    for entity in load_directory(path)["entities"].values():
        if entity.get("state") in {"retired", "superseded", "stale"}:
            continue
        if capability in entity.get("owns", []) or capability in entity.get("provides", []):
            out.append(entity)
    return sorted(out, key=lambda e: (not bool(e.get("authority", {}).get("exclusive")), e["id"]))


def mark_verified(entity_id: str, state: str = "verified", *, path: Path = REGISTRY_PATH, metadata: dict | None = None) -> dict:
    if state not in VALID_STATES:
        raise ValueError(state)
    data = load_directory(path)
    entity = data["entities"].get(entity_id)
    if not entity:
        raise KeyError(entity_id)
    entity["state"] = state
    entity["last_verified_at"] = _now()
    if metadata:
        entity.setdefault("metadata", {}).update(metadata)
    save_directory(data, path)
    return entity


def sync_roles_from_canonical_registry(path: Path = REGISTRY_PATH) -> None:
    """Mirror canonical role contracts into the query directory.

    `.agent/roles/registry.yaml` remains the source of truth for role semantics.
    The Governance Directory is a runtime/query index, not a second role authority.
    """
    if yaml is None or not ROLE_REGISTRY_PATH.exists():
        return
    data = yaml.safe_load(ROLE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    role_set_version = str(data.get("role_set_version") or "unknown")
    for role in data.get("roles", []) or []:
        if not isinstance(role, dict) or not role.get("id"):
            continue
        rid = str(role["id"])
        status = str(role.get("status") or "active")
        state = "declared" if status in {"active", "proposed"} else "retired"
        if status == "stale":
            state = "stale"
        raw_caps = role.get("capabilities") or []
        provides = [f"capability://{c}" if not str(c).startswith("capability://") else str(c) for c in raw_caps]
        entity = GovernanceEntity(
            id=f"role://{rid}",
            kind="role",
            name=str(role.get("name") or rid),
            owns=[],
            provides=provides,
            implementation={
                "canonical_registry": str(ROLE_REGISTRY_PATH.relative_to(PROJECT_ROOT)),
                "source": role.get("source"),
            },
            authority={"exclusive": False, "canonical_role_contract": True},
            state=state,
            metadata={
                "role_status": status,
                "role_kind": role.get("kind"),
                "purpose": role.get("purpose"),
                "role_set_version": role_set_version,
                "must_obey": role.get("must_obey") or [],
            },
        )
        upsert(entity, path=path)

    for legacy in data.get("legacy_instances", []) or []:
        if not isinstance(legacy, dict) or not legacy.get("id"):
            continue
        entity = GovernanceEntity(
            id=f"role://{legacy['id']}",
            kind="role",
            name=str(legacy["id"]),
            owns=[],
            provides=[],
            implementation={"source": legacy.get("source"), "canonical_registry": str(ROLE_REGISTRY_PATH.relative_to(PROJECT_ROOT))},
            authority={"exclusive": False, "canonical_role_contract": True},
            state="stale" if legacy.get("status") == "stale" else "retired",
            metadata={"reason": legacy.get("reason"), "role_set_version": role_set_version},
        )
        upsert(entity, path=path)


def seed_core(path: Path = REGISTRY_PATH) -> None:
    # Roles are mirrored from the canonical versioned role registry, never hand-copied here.
    sync_roles_from_canonical_registry(path)

    core: Iterable[GovernanceEntity] = [
        GovernanceEntity(
            id="manager://port",
            kind="manager",
            name="AgentOS Port Manager",
            owns=["capability://network.port.allocate", "capability://network.port.register", "capability://network.port.release"],
            provides=["capability://network.port.allocate", "capability://network.port.register", "capability://network.port.release"],
            implementation={"repo":"alston-personal/agentmanager", "path":"scripts/core_services/port_manager.py", "state_path":"/home/ubuntu/agent-data/config/port_registry.json"},
            authority={"exclusive": True, "governance_required": True},
            state="implemented",
            owner="role://sector.paw",
        ),
        GovernanceEntity(
            id="service://agentos.watchdog",
            kind="service",
            name="AgentOS Watchdog",
            owns=["capability://runtime.health.monitor", "capability://runtime.self-heal"],
            provides=["capability://runtime.health.monitor", "capability://runtime.self-heal"],
            implementation={"repo":"alston-personal/agentmanager", "path":"scripts/os_watchdog.py", "registry":".agent/SERVICES.md"},
            authority={"exclusive": True, "governance_required": True},
            state="implemented",
            owner="role://governance.keeper",
        ),
        GovernanceEntity(
            id="policy://discover-before-invent",
            kind="policy",
            name="Discover Before Invent",
            owns=[],
            provides=[],
            implementation={"rule":"Resolve owner/capability before new implementation; discover and register only when unresolved."},
            authority={"exclusive": False},
            state="declared",
            owner="role://governance.keeper",
        ),
    ]
    for entity in core:
        upsert(entity, path=path)


if __name__ == "__main__":
    seed_core()
    print(REGISTRY_PATH)
