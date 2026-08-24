"""Portable AgentOS Node identity and capability contracts.

A discovered device or service is not authority.  These contracts intentionally
separate observation, registration, authorization, and activation so a Node can
report what exists without self-granting permission to use it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any


NODE_SCHEMA = "agentos.node/v1"
CAPABILITY_MANIFEST_SCHEMA = "agentos.node-capability-manifest/v1"
CAPABILITY_DELTA_SCHEMA = "agentos.node-capability-delta/v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _content_id(prefix: str, value: Any) -> str:
    return prefix + sha256(_canonical(value).encode("utf-8")).hexdigest()[:32]


class CapabilityState(str, Enum):
    DISCOVERED = "discovered"
    REGISTERED = "registered"
    AUTHORIZED = "authorized"
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class NodeIdentity:
    node_id: str
    realm_id: str
    hostname: str
    platform: str
    arch: str
    profile: str = "edge"
    labels: tuple[str, ...] = ()
    schema_version: str = NODE_SCHEMA

    def __post_init__(self) -> None:
        required = (self.node_id, self.realm_id, self.hostname, self.platform, self.arch, self.profile)
        if any(not value.strip() for value in required):
            raise ValueError("node identity fields are required")

    @property
    def identity_id(self) -> str:
        return _content_id("node_", asdict(self))


@dataclass(frozen=True)
class CapabilityObservation:
    capability: str
    source: str
    state: CapabilityState = CapabilityState.DISCOVERED
    device_ref: str | None = None
    adapter: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    risk_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.capability.strip() or not self.source.strip():
            raise ValueError("capability and source are required")
        if self.state in {CapabilityState.AUTHORIZED, CapabilityState.ACTIVE}:
            raise ValueError("discovery input may not self-authorize or self-activate")


@dataclass(frozen=True)
class NodeCapabilityManifest:
    identity: NodeIdentity
    observed_at: str
    capabilities: tuple[CapabilityObservation, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CAPABILITY_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if not self.observed_at.strip():
            raise ValueError("observed_at is required")
        names = [item.capability for item in self.capabilities]
        if len(names) != len(set(names)):
            raise ValueError("capabilities must be unique per manifest")

    @property
    def manifest_id(self) -> str:
        return _content_id("ncap_", asdict(self))

    def capability(self, name: str) -> CapabilityObservation | None:
        return next((item for item in self.capabilities if item.capability == name), None)


@dataclass(frozen=True)
class CapabilityChange:
    capability: str
    before: CapabilityState | None
    after: CapabilityState | None


@dataclass(frozen=True)
class NodeCapabilityDelta:
    node_id: str
    previous_manifest_id: str
    current_manifest_id: str
    changes: tuple[CapabilityChange, ...]
    schema_version: str = CAPABILITY_DELTA_SCHEMA


def diff_manifests(previous: NodeCapabilityManifest, current: NodeCapabilityManifest) -> NodeCapabilityDelta:
    if previous.identity.node_id != current.identity.node_id:
        raise ValueError("cannot diff manifests from different nodes")
    old = {item.capability: item for item in previous.capabilities}
    new = {item.capability: item for item in current.capabilities}
    changes: list[CapabilityChange] = []
    for name in sorted(set(old) | set(new)):
        before = old.get(name)
        after = new.get(name)
        if before is None:
            changes.append(CapabilityChange(name, None, after.state))
        elif after is None:
            changes.append(CapabilityChange(name, before.state, None))
        elif before.state != after.state or before.attributes != after.attributes or before.device_ref != after.device_ref:
            changes.append(CapabilityChange(name, before.state, after.state))
    return NodeCapabilityDelta(
        node_id=current.identity.node_id,
        previous_manifest_id=previous.manifest_id,
        current_manifest_id=current.manifest_id,
        changes=tuple(changes),
    )
