from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


WAKE_INTENT_SCHEMA = "agentos.employee-wake-intent/v1"
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
FORBIDDEN_KEYS = {
    "argv",
    "executable",
    "command",
    "shell",
    "url",
    "endpoint",
    "credential",
    "credentials",
    "token",
    "secret",
    "authorization",
    "headers",
    "env",
    "environment",
    "node_id",
    "provider",
    "model",
    "session_id",
}
SECRET_MARKERS = (
    "bearer ",
    "github_pat_",
    "ghp_",
    "token=",
    "secret=",
    "authorization:",
)


def _safe_id(value: str) -> str:
    value = str(value or "").strip()
    if not value or any(ch in value for ch in "/\\\0") or value in {".", ".."}:
        raise ValueError("unsafe_employee_wake_id")
    return value


def _walk_safe(value: Any, *, path: str = "wake_intent") -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().casefold()
            if key in FORBIDDEN_KEYS:
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


def _digest(intent: dict[str, Any]) -> str:
    raw = json.dumps(intent, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deliver_employee_wake(task: dict[str, Any], root: Path) -> dict[str, Any]:
    intent = task.get("wake_intent")
    if not isinstance(intent, dict):
        raise ValueError("employee_wake_intent_required")
    if intent.get("schema") != WAKE_INTENT_SCHEMA:
        raise ValueError("invalid_employee_wake_intent_schema")
    unexpected = sorted(set(intent) - ALLOWED_INTENT_KEYS)
    if unexpected:
        raise ValueError("unexpected_employee_wake_fields:" + ",".join(unexpected))
    _walk_safe(intent)

    wake_id = _safe_id(intent.get("wake_id"))
    employee_id = _safe_id(intent.get("employee_id"))
    assignment_id = _safe_id(intent.get("assignment_id"))
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
    generation = int(intent.get("expected_lease_generation") or 0)
    if generation < 1:
        raise ValueError("employee_wake_generation_invalid")

    digest = _digest(intent)
    path = Path(root) / employee_id / f"{wake_id}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("digest") != digest:
            raise RuntimeError("employee_wake_idempotency_conflict")
    else:
        _atomic_write(
            path,
            {
                "schema": WAKE_RECEIPT_SCHEMA,
                "wake_id": wake_id,
                "employee_id": employee_id,
                "assignment_id": assignment_id,
                "expected_lease_generation": generation,
                "digest": digest,
                "wake_intent": intent,
            },
        )
    return {
        "wake_delivery": {
            "schema": WAKE_RECEIPT_SCHEMA,
            "wake_id": wake_id,
            "employee_id": employee_id,
            "assignment_id": assignment_id,
            "expected_lease_generation": generation,
            "accepted": True,
            "digest": digest,
            "executor_invoked": False,
            "credential_exposed": False,
        }
    }
