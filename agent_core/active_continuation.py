from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.resolve_facade import resolve_continuation

SELECTOR_SCHEMA = "agentos.active-continuation/v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _data_root(value: str | Path | None = None) -> Path:
    if value is not None:
        return Path(value)
    return Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))


def selector_path(data_root: str | Path | None = None) -> Path:
    return _data_root(data_root) / "runtime" / "active-continuation.json"


def _validate_pointer(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("active continuation selector must be an object")
    if value.get("schema") != SELECTOR_SCHEMA:
        raise ValueError("unsupported active continuation selector schema")
    project_id = str(value.get("project_id") or "").strip()
    index_id = str(value.get("index_id") or "").strip()
    ir_id = str(value.get("ir_id") or "").strip()
    if not all((project_id, index_id, ir_id)):
        raise ValueError("active continuation selector requires project_id, index_id, and ir_id")
    return {
        "schema": SELECTOR_SCHEMA,
        "project_id": project_id,
        "index_id": index_id,
        "ir_id": ir_id,
        "activated_at": value.get("activated_at"),
        "reason": value.get("reason"),
    }


def read_active_continuation(data_root: str | Path | None = None) -> dict[str, Any]:
    path = selector_path(data_root)
    if path.is_symlink():
        raise ValueError("active continuation selector may not be a symlink")
    if not path.is_file():
        raise FileNotFoundError(f"active continuation selector missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_pointer(payload)


def _current_generation(project_id: str, *, data_root: str | Path | None = None) -> tuple[dict[str, Any], str, str]:
    resolved = resolve_continuation(project_id, data_root=data_root)
    head = resolved.get("execution_head") if isinstance(resolved.get("execution_head"), dict) else {}
    continuation = resolved.get("continuation") if isinstance(resolved.get("continuation"), dict) else {}
    ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else {}
    index_id = str(head.get("index_id") or "").strip()
    ir_id = str(ir.get("ir_id") or "").strip()
    if not index_id or not ir_id:
        raise ValueError("selected project has no valid canonical continuation generation")
    if str(ir.get("index_id") or "").strip() != index_id:
        raise ValueError("selected project execution-head / IR generation mismatch")
    return resolved, index_id, ir_id


def resolve_active_continuation(
    *,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    selector = read_active_continuation(data_root)
    resolved, index_id, ir_id = _current_generation(selector["project_id"], data_root=data_root)
    if selector["index_id"] != index_id or selector["ir_id"] != ir_id:
        raise ValueError(
            "active continuation selector is stale: "
            f"selector={selector['index_id']}/{selector['ir_id']} "
            f"canonical={index_id}/{ir_id}"
        )
    return {"selector": selector, "resolution": resolved}


def activate_continuation(
    project_id: str,
    *,
    index_id: str,
    ir_id: str,
    reason: str,
    data_root: str | Path | None = None,
) -> dict[str, Any]:
    project_id = str(project_id or "").strip()
    index_id = str(index_id or "").strip()
    ir_id = str(ir_id or "").strip()
    reason = str(reason or "").strip()
    if not all((project_id, index_id, ir_id, reason)):
        raise ValueError("activate_continuation requires project_id, index_id, ir_id, and reason")

    root = _data_root(data_root)
    _, current_index, current_ir = _current_generation(project_id, data_root=root)
    if current_index != index_id or current_ir != ir_id:
        raise ValueError(
            "refusing to activate a non-canonical generation: "
            f"requested={index_id}/{ir_id} canonical={current_index}/{current_ir}"
        )

    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    path = selector_path(root)
    if path.is_symlink():
        raise ValueError("active continuation selector may not be a symlink")
    lock_path = runtime / ".active-continuation.lock"
    if lock_path.is_symlink():
        raise ValueError("active continuation lock may not be a symlink")

    payload = {
        "schema": SELECTOR_SCHEMA,
        "project_id": project_id,
        "index_id": index_id,
        "ir_id": ir_id,
        "activated_at": _now(),
        "reason": reason,
    }

    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o640)
    previous: dict[str, Any] | None = None
    tmp: Path | None = None
    try:
        with os.fdopen(lock_fd, "r+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            if path.is_file():
                previous = _validate_pointer(json.loads(path.read_text(encoding="utf-8")))
            fd, raw = tempfile.mkstemp(prefix=".active-continuation.", suffix=".tmp", dir=str(runtime))
            tmp = Path(raw)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o640)
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
            tmp = None
            dir_fd = os.open(runtime, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)

    return {
        "schema": "agentos.active-continuation-activation/v1",
        "ok": True,
        "selector": payload,
        "previous": previous,
        "credential_exposed": False,
    }
