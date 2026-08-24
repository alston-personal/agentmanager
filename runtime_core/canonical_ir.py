"""Canonical, transport-neutral IR for Distributed AgentOS.

The IR is intentionally JSON-safe and host-agnostic. It is the handoff contract
between agents, devices, web adapters, and remote runtime workers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Dict, List
import uuid


SCHEMA_VERSION = "agentos.ir/v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class CanonicalIR:
    goal: str
    project_id: str
    capability: str
    payload: Dict[str, Any] = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    pending_tasks: List[Dict[str, Any]] = field(default_factory=list)
    continuation: Dict[str, Any] = field(default_factory=dict)
    ir_id: str = field(default_factory=lambda: f"ir_{uuid.uuid4().hex}")
    parent_ir_id: str | None = None
    hop_count: int = 0
    created_at: str = field(default_factory=_utc_now)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.hop_count < 0:
            raise ValueError("hop_count cannot be negative")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def digest(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalIR":
        if data.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ValueError(f"unsupported Canonical IR schema: {data.get('schema_version')}")
        required = ("goal", "project_id", "capability")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"missing Canonical IR fields: {', '.join(missing)}")
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in allowed})

    @classmethod
    def from_json(cls, raw: str) -> "CanonicalIR":
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Canonical IR JSON root must be an object")
        return cls.from_dict(value)

    def derive_continuation(
        self,
        *,
        payload: Dict[str, Any] | None = None,
        continuation: Dict[str, Any] | None = None,
        capability: str | None = None,
    ) -> "CanonicalIR":
        """Create the next immutable handoff while preserving lineage."""
        return CanonicalIR(
            goal=self.goal,
            project_id=self.project_id,
            capability=capability or self.capability,
            payload=payload or {},
            constraints=list(self.constraints),
            context=dict(self.context),
            artifacts=list(self.artifacts),
            decisions=list(self.decisions),
            pending_tasks=list(self.pending_tasks),
            continuation=continuation or {},
            parent_ir_id=self.ir_id,
            hop_count=self.hop_count + 1,
        )
