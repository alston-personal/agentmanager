from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
REGISTRY_PATH = DATA_ROOT / "governance" / "directory.json"

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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register(entity: GovernanceEntity, *, replace: bool = False, path: Path = REGISTRY_PATH) -> GovernanceEntity:
    entity.validate()
    data = load_directory(path)
    current = data["entities"].get(entity.id)
    if current and not replace:
        raise ValueError(f"entity already exists: {entity.id}")

    # Enforce exclusive ownership before write.
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


def get(entity_id: str, path: Path = REGISTRY_PATH) -> dict | None:
    return load_directory(path)["entities"].get(entity_id)


def list_entities(kind: str | None = None, path: Path = REGISTRY_PATH) -> list[dict]:
    values = list(load_directory(path)["entities"].values())
    if kind:
        values = [v for v in values if v.get("kind") == kind]
    return sorted(values, key=lambda x: x["id"])


def resolve(capability: str, path: Path = REGISTRY_PATH) -> list[dict]:
    """Resolve who owns/provides a capability. Active exclusive owners sort first."""
    out = []
    for entity in load_directory(path)["entities"].values():
        if entity.get("state") in {"retired", "superseded"}:
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


def seed_core(path: Path = REGISTRY_PATH) -> None:
    core: Iterable[GovernanceEntity] = [
        GovernanceEntity(
            id="manager://port",
            kind="manager",
            name="AgentOS Port Manager",
            owns=["capability://network.port.allocate", "capability://network.port.register", "capability://network.port.release"],
            provides=[],
            implementation={"repo":"alston-personal/agentmanager", "path":"scripts/core_services/port_manager.py", "state_path":"/home/ubuntu/agent-data/config/port_registry.json"},
            authority={"exclusive": True, "governance_required": True},
            state="implemented",
            owner="role://agentos.paw",
        ),
        GovernanceEntity(
            id="role://agentos.spec-steward",
            kind="role",
            name="AgentOS Spec Steward",
            owns=["capability://governance.spec.audit", "capability://governance.spec.drift-detect"],
            provides=["capability://governance.spec.audit"],
            implementation={"repo":"alston-personal/agentmanager", "path":"scripts/spec_steward.py", "definition":".agent/roles/instances/agentos_spec_steward.md"},
            authority={"exclusive": True, "governance_required": False},
            state="implemented",
        ),
        GovernanceEntity(
            id="role://agentos.weaver",
            kind="role",
            name="LCS Weaver",
            owns=["capability://governance.spec.define", "capability://architecture.design"],
            provides=["capability://governance.spec.define", "capability://architecture.design"],
            implementation={"definition":".agent/roles/parents/lcs_weaver.md"},
            authority={"exclusive": False},
            state="declared",
        ),
        GovernanceEntity(
            id="role://agentos.paw",
            kind="role",
            name="LCS The Paw",
            owns=["capability://implementation.code", "capability://implementation.automation"],
            provides=["capability://implementation.code", "capability://implementation.automation"],
            implementation={"definition":".agent/roles/parents/lcs_the_paw.md"},
            authority={"exclusive": False},
            state="declared",
        ),
        GovernanceEntity(
            id="role://agentos.claw",
            kind="role",
            name="LCS The Claw",
            owns=["capability://security.audit", "capability://validation.breaking-test"],
            provides=["capability://security.audit", "capability://validation.breaking-test"],
            implementation={"definition":".agent/roles/parents/lcs_the_claw.md"},
            authority={"exclusive": False},
            state="declared",
        ),
        GovernanceEntity(
            id="role://agentos.whisperer",
            kind="role",
            name="LCS Whisperer",
            owns=["capability://ideation.prototype", "capability://ux.concept"],
            provides=["capability://ideation.prototype", "capability://ux.concept"],
            implementation={"definition":".agent/roles/parents/lcs_whisperer.md"},
            authority={"exclusive": False},
            state="declared",
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
        ),
    ]
    for entity in core:
        if get(entity.id, path) is None:
            register(entity, path=path)


if __name__ == "__main__":
    seed_core()
    print(REGISTRY_PATH)
