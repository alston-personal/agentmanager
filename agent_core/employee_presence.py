from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent_core.employee_runtime import EmployeeRuntime


PRESENCE_SCHEMA = "agentos.employee-presence/v1"
WAKE_CAPABILITY = "agent.employee.wake.deliver"
MIN_TTL_SECONDS = 30
MAX_TTL_SECONDS = 900


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _safe_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError("unsafe_employee_presence_id")
    return value


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


@dataclass(frozen=True, slots=True)
class EmployeePresence:
    schema: str
    employee_id: str
    node_id: str
    presence_id: str
    generation: int
    bound_at: str
    heartbeat_at: str
    expires_at: str
    required_capability: str = WAKE_CAPABILITY
    executor_identity_bound: bool = False
    credential_exposed: bool = False


class EmployeePresenceRegistry:
    """ONE-side ephemeral Employee -> Node location, never Employee identity.

    A presence lease only says which currently-online Node has declared the fixed
    Employee wake inbox capability.  It does not bind an executor/model/session
    and it does not grant the Node any Employee assignment authority.
    """

    def __init__(self, runtime: EmployeeRuntime, node_registry: Any) -> None:
        self.runtime = runtime
        self.node_registry = node_registry
        self.root = runtime.root / "realm" / "employee-presence"

    def _path(self, employee_id: str) -> Path:
        return self.root / f"{_safe_id(employee_id)}.json"

    def get(self, employee_id: str) -> EmployeePresence | None:
        path = self._path(employee_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != PRESENCE_SCHEMA:
            raise ValueError("employee_presence_state_invalid")
        return EmployeePresence(**payload)

    def _eligible_node(self, node_id: str) -> dict[str, Any]:
        node_id = _safe_id(node_id)
        node_map = self.node_registry.node_map()
        node = next(
            (item for item in node_map.get("nodes", []) if item.get("node_id") == node_id),
            None,
        )
        if node is None:
            raise KeyError(node_id)
        if node.get("status") != "online":
            raise RuntimeError("employee_presence_node_not_online")
        if WAKE_CAPABILITY not in set(node.get("capabilities") or []):
            raise PermissionError("employee_presence_node_lacks_wake_capability")
        return node

    def bind(
        self,
        employee_id: str,
        node_id: str,
        presence_id: str,
        *,
        ttl_seconds: int = 120,
        supersede_presence_id: str | None = None,
        now: datetime | None = None,
    ) -> EmployeePresence:
        employee_id = _safe_id(employee_id)
        node_id = _safe_id(node_id)
        presence_id = _safe_id(presence_id)
        self.runtime.get_employee(employee_id)
        self._eligible_node(node_id)
        ttl = int(ttl_seconds)
        if ttl < MIN_TTL_SECONDS or ttl > MAX_TTL_SECONDS:
            raise ValueError("employee_presence_ttl_out_of_range")
        current = now or _utcnow()
        existing = self.get(employee_id)

        if existing and existing.presence_id == presence_id:
            if existing.node_id != node_id:
                raise RuntimeError("employee_presence_id_node_mismatch")
            return self.heartbeat(
                employee_id,
                presence_id,
                ttl_seconds=ttl,
                now=current,
            )

        generation = 1
        if existing:
            generation = existing.generation + 1
            live = _parse(existing.expires_at) > current
            if live and supersede_presence_id != existing.presence_id:
                raise RuntimeError("employee_presence_already_live")

        presence = EmployeePresence(
            schema=PRESENCE_SCHEMA,
            employee_id=employee_id,
            node_id=node_id,
            presence_id=presence_id,
            generation=generation,
            bound_at=_iso(current),
            heartbeat_at=_iso(current),
            expires_at=_iso(current + timedelta(seconds=ttl)),
        )
        _atomic_write(self._path(employee_id), asdict(presence))
        return presence

    def heartbeat(
        self,
        employee_id: str,
        presence_id: str,
        *,
        ttl_seconds: int = 120,
        now: datetime | None = None,
    ) -> EmployeePresence:
        employee_id = _safe_id(employee_id)
        presence_id = _safe_id(presence_id)
        current = now or _utcnow()
        ttl = int(ttl_seconds)
        if ttl < MIN_TTL_SECONDS or ttl > MAX_TTL_SECONDS:
            raise ValueError("employee_presence_ttl_out_of_range")
        existing = self.get(employee_id)
        if existing is None or existing.presence_id != presence_id:
            raise PermissionError("employee_presence_not_owned")
        self._eligible_node(existing.node_id)
        if _parse(existing.expires_at) <= current:
            raise RuntimeError("employee_presence_expired")
        updated = EmployeePresence(
            **{
                **asdict(existing),
                "heartbeat_at": _iso(current),
                "expires_at": _iso(current + timedelta(seconds=ttl)),
            }
        )
        _atomic_write(self._path(employee_id), asdict(updated))
        return updated

    def resolve(self, employee_id: str, *, now: datetime | None = None) -> EmployeePresence:
        employee_id = _safe_id(employee_id)
        self.runtime.get_employee(employee_id)
        current = now or _utcnow()
        presence = self.get(employee_id)
        if presence is None:
            raise RuntimeError("employee_presence_unavailable")
        if _parse(presence.expires_at) <= current:
            raise RuntimeError("employee_presence_expired")
        self._eligible_node(presence.node_id)
        return presence
