from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.controller_service import ControllerService
from agent_core.employee_presence import EmployeePresenceRegistry, WAKE_CAPABILITY
from agent_core.employee_wake import EmployeeWakeIntent


DELIVERY_SCHEMA = "agentos.employee-wake-delivery-state/v1"
PRESENCE_ROUTE_SCHEMA = "agentos.employee-wake-route/v1"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _utcnow()).astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError("unsafe_employee_wake_delivery_id")
    return value


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != DELIVERY_SCHEMA:
        raise ValueError("employee_wake_delivery_state_invalid")
    return payload


def _attempt_id(wake_id: str, presence_generation: int, node_id: str) -> str:
    digest = hashlib.sha256(f"{wake_id}\0{presence_generation}\0{node_id}".encode("utf-8")).hexdigest()[:24]
    return "wakedelivery_" + digest


def _task_id(wake_id: str, presence_generation: int) -> str:
    digest = hashlib.sha256(f"{wake_id}\0{presence_generation}".encode("utf-8")).hexdigest()[:24]
    return "empwake_" + digest


@dataclass(slots=True)
class EmployeeWakeDeliveryState:
    schema: str
    attempt_id: str
    wake_id: str
    employee_id: str
    assignment_id: str
    presence_id: str
    presence_generation: int
    node_id: str
    task_id: str
    status: str
    attempted_at: str
    updated_at: str
    queued_at: str | None = None
    completed_at: str | None = None
    node_ok: bool | None = None
    node_wake_accepted: bool | None = None
    error_code: str | None = None
    controller_entered: bool | None = None
    credential_exposed: bool = False


class EmployeeWakeDelivery:
    """Deliver one exact durable Employee wake intent through existing ONE Node queue.

    This layer does not re-plan work. Its input is the exact wake intent already
    selected/journaled by Core. Delivery is scoped by Employee presence generation.
    A crash after persisting `dispatching` is UNKNOWN and is not blindly retried to
    that same presence generation.
    """

    def __init__(self, presence: EmployeePresenceRegistry, controller: ControllerService) -> None:
        self.presence = presence
        self.controller = controller
        self.root = presence.runtime.root / "realm" / "employee-wake-delivery"

    def _path(self, wake_id: str, presence_generation: int) -> Path:
        return self.root / _safe_id(wake_id) / f"{int(presence_generation):06d}.json"

    def get(self, wake_id: str, presence_generation: int) -> EmployeeWakeDeliveryState | None:
        payload = _read(self._path(wake_id, presence_generation))
        return EmployeeWakeDeliveryState(**payload) if payload else None

    def deliver_intent(
        self,
        intent: EmployeeWakeIntent,
        *,
        now: datetime | None = None,
    ) -> EmployeeWakeDeliveryState:
        if not isinstance(intent, EmployeeWakeIntent):
            raise TypeError("employee_wake_intent_type_required")
        current = now or _utcnow()
        route = self.presence.resolve(intent.employee_id, now=current)
        path = self._path(intent.wake_id, route.generation)
        existing = _read(path)
        if existing is not None:
            state = EmployeeWakeDeliveryState(**existing)
            if state.status == "dispatching":
                state.status = "unknown"
                state.error_code = "dispatch_interrupted_after_claim"
                state.updated_at = _iso(current)
                _atomic_write(path, asdict(state))
            return state

        state = EmployeeWakeDeliveryState(
            schema=DELIVERY_SCHEMA,
            attempt_id=_attempt_id(intent.wake_id, route.generation, route.node_id),
            wake_id=intent.wake_id,
            employee_id=intent.employee_id,
            assignment_id=intent.assignment_id,
            presence_id=route.presence_id,
            presence_generation=route.generation,
            node_id=route.node_id,
            task_id=_task_id(intent.wake_id, route.generation),
            status="dispatching",
            attempted_at=_iso(current),
            updated_at=_iso(current),
        )
        _atomic_write(path, asdict(state))

        wake_route = {
            "schema": PRESENCE_ROUTE_SCHEMA,
            "employee_id": route.employee_id,
            "node_id": route.node_id,
            "presence_id": route.presence_id,
            "presence_generation": route.generation,
        }
        request = {
            "schema": ControllerService.REQUEST_SCHEMA,
            "node_id": route.node_id,
            "action": WAKE_CAPABILITY,
            "task_id": state.task_id,
            "payload": {
                "wake_intent": intent.as_dict(),
                "employee_wake_route": wake_route,
            },
        }
        try:
            result = self.controller.dispatch(request)
        except Exception:
            # Crossing the durable ONE queue boundary can be ambiguous. Do not
            # serialize exception text and do not blindly retry the same route.
            state.status = "unknown"
            state.error_code = "controller_dispatch_uncertain"
            state.updated_at = _iso(current)
            _atomic_write(path, asdict(state))
            return state

        state.status = "queued"
        state.queued_at = str(result.get("queued_at") or _iso(current))
        state.controller_entered = bool(result.get("controller_entered"))
        state.updated_at = _iso(current)
        _atomic_write(path, asdict(state))
        return state

    def reconcile(
        self,
        wake_id: str,
        presence_generation: int,
        *,
        now: datetime | None = None,
    ) -> EmployeeWakeDeliveryState:
        state = self.get(wake_id, presence_generation)
        if state is None:
            raise FileNotFoundError(wake_id)
        receipt = self.controller.fabric.get_receipt(state.task_id)
        if receipt is None:
            return state

        current = now or _utcnow()
        valid_identity = (
            receipt.get("schema") == "agentos.node-receipt/v0.1"
            and receipt.get("task_id") == state.task_id
            and receipt.get("node_id") == state.node_id
            and receipt.get("action") == WAKE_CAPABILITY
        )
        if not valid_identity:
            state.status = "unknown"
            state.error_code = "node_receipt_identity_mismatch"
        else:
            wake_receipt = receipt.get("wake_delivery")
            accepted = bool(
                isinstance(wake_receipt, dict)
                and wake_receipt.get("wake_id") == state.wake_id
                and wake_receipt.get("employee_id") == state.employee_id
                and wake_receipt.get("assignment_id") == state.assignment_id
                and wake_receipt.get("node_id") == state.node_id
                and wake_receipt.get("presence_id") == state.presence_id
                and wake_receipt.get("presence_generation") == state.presence_generation
                and wake_receipt.get("accepted") is True
                and wake_receipt.get("executor_invoked") is False
                and wake_receipt.get("credential_exposed") is False
            )
            state.node_ok = receipt.get("ok") is True
            state.node_wake_accepted = accepted
            if state.node_ok and accepted:
                state.status = "delivered"
                state.error_code = None
            else:
                state.status = "failed"
                state.error_code = "node_wake_delivery_failed"
        state.completed_at = _iso(current)
        state.updated_at = _iso(current)
        _atomic_write(self._path(wake_id, presence_generation), asdict(state))
        return state
