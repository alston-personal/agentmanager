from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


WAKE_INTENT_SCHEMA = "agentos.employee-wake-intent/v1"
WAKE_ROUTE_SCHEMA = "agentos.employee-wake-route/v1"
WAKE_RECEIPT_SCHEMA = "agentos.employee-wake-delivery/v1"
ALLOWED_INTENT_KEYS = {
    "schema",
    "wake_id",
    "employee_id",
    "assignment_id",
    "mode",
    "expected_lease_generation",
    "goal",
    "thread_head",
    "constraints",
    "role_ids",
    "skill_ids",
    "resume_required",
    "prior_execution_state",
    "authority_boundary",
    "executor_selection",
    "transport_selection",
    "credential_exposed",
}
ROUTE_KEYS = {"schema", "employee_id", "node_id", "presence_id", "presence_generation"}
FORBIDDEN_INTENT_KEYS = {
    "argv", "executable", "command", "shell", "url", "endpoint", "credential",
    "credentials", "token", "secret", "authorization", "headers", "env",
    "environment", "node_id", "provider", "model", "session_id",
}
SECRET_MARKERS = ("bearer ", "github_pat_", "ghp_", "token=", "secret=", "authorization:")


def _safe_id(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 256 or any(ch in text for ch in "/\\\0") or text in {".", ".."}:
        raise ValueError(f"invalid_{field}")
    return text


def _walk_safe(value: Any, *, path: str = "wake_intent") -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().casefold()
            if key in FORBIDDEN_INTENT_KEYS:
                raise ValueError(f"forbidden_employee_wake_field:{path}.{key}")
            _walk_safe(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        if len(value) > 128:
            raise ValueError("employee_wake_list_too_large")
        for index, item in enumerate(value):
            _walk_safe(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str):
        if len(value) > 4096:
            raise ValueError("employee_wake_string_too_large")
        lowered = value.casefold()
        if any(marker in lowered for marker in SECRET_MARKERS):
            raise ValueError(f"employee_wake_secret_like_value:{path}")
        return
    if value is None or isinstance(value, (bool, int, float)):
        return
    raise ValueError(f"unsupported_employee_wake_value:{path}")


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _digest(intent: dict[str, Any], route: dict[str, Any]) -> str:
    raw = json.dumps(
        {"wake_intent": intent, "employee_wake_route": route},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deliver_employee_wake(task: dict[str, Any], root: Path, *, expected_node_id: str) -> dict[str, Any]:
    """Persist one bounded wake capsule; never start or select an executor."""
    intent = task.get("wake_intent")
    route = task.get("employee_wake_route")
    if not isinstance(intent, dict):
        raise ValueError("employee_wake_intent_required")
    if not isinstance(route, dict):
        raise ValueError("employee_wake_route_required")
    if intent.get("schema") != WAKE_INTENT_SCHEMA:
        raise ValueError("invalid_employee_wake_intent_schema")
    if route.get("schema") != WAKE_ROUTE_SCHEMA:
        raise ValueError("invalid_employee_wake_route_schema")

    unexpected_intent = sorted(set(intent) - ALLOWED_INTENT_KEYS)
    if unexpected_intent:
        raise ValueError("unexpected_employee_wake_fields:" + ",".join(unexpected_intent))
    unexpected_route = sorted(set(route) - ROUTE_KEYS)
    if unexpected_route:
        raise ValueError("unexpected_employee_wake_route_fields:" + ",".join(unexpected_route))
    _walk_safe(intent)

    wake_id = _safe_id(intent.get("wake_id"), field="wake_id")
    employee_id = _safe_id(intent.get("employee_id"), field="employee_id")
    assignment_id = _safe_id(intent.get("assignment_id"), field="assignment_id")
    route_employee_id = _safe_id(route.get("employee_id"), field="route_employee_id")
    route_node_id = _safe_id(route.get("node_id"), field="route_node_id")
    presence_id = _safe_id(route.get("presence_id"), field="presence_id")
    local_node_id = _safe_id(expected_node_id, field="expected_node_id")
    if route_employee_id != employee_id:
        raise PermissionError("employee_wake_route_employee_mismatch")
    if route_node_id != local_node_id:
        raise PermissionError("employee_wake_route_node_mismatch")
    generation_raw = route.get("presence_generation")
    if isinstance(generation_raw, bool) or not isinstance(generation_raw, int) or generation_raw < 1:
        raise ValueError("employee_wake_presence_generation_invalid")
    presence_generation = generation_raw

    if intent.get("authority_boundary") != "selection_only_no_execution":
        raise ValueError("employee_wake_authority_boundary_invalid")
    if intent.get("executor_selection") != "unbound":
        raise ValueError("employee_wake_executor_must_be_unbound")
    if intent.get("transport_selection") != "unbound":
        raise ValueError("employee_wake_transport_must_be_unbound")
    if intent.get("credential_exposed") is not False:
        raise ValueError("employee_wake_credential_boundary_invalid")
    if intent.get("mode") not in {"fresh", "resume"}:
        raise ValueError("employee_wake_mode_invalid")
    lease_generation = intent.get("expected_lease_generation")
    if isinstance(lease_generation, bool) or not isinstance(lease_generation, int) or lease_generation < 1:
        raise ValueError("employee_wake_generation_invalid")

    digest = _digest(intent, route)
    path = Path(root) / employee_id / f"{wake_id}.{presence_generation:06d}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("digest") != digest:
            raise RuntimeError("employee_wake_idempotency_conflict")
    else:
        _atomic_write(
            path,
            {
                "schema": WAKE_RECEIPT_SCHEMA,
                "wake_id": wake_id,
                "employee_id": employee_id,
                "assignment_id": assignment_id,
                "node_id": route_node_id,
                "presence_id": presence_id,
                "presence_generation": presence_generation,
                "expected_lease_generation": lease_generation,
                "digest": digest,
                "wake_intent": intent,
                "employee_wake_route": route,
            },
        )

    return {
        "wake_delivery": {
            "schema": WAKE_RECEIPT_SCHEMA,
            "wake_id": wake_id,
            "employee_id": employee_id,
            "assignment_id": assignment_id,
            "node_id": route_node_id,
            "presence_id": presence_id,
            "presence_generation": presence_generation,
            "expected_lease_generation": lease_generation,
            "accepted": True,
            "digest": digest,
            "executor_invoked": False,
            "credential_exposed": False,
        }
    }
