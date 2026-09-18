#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any

SELECTOR_SCHEMA = "agentos.active-continuation/v1"
EXECUTION_HEAD_SCHEMA = "agentos.execution-head/v1"
IR_SCHEMA = "agentos.ir/v1"
PROJECT_ID = "agentos-core"


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError(f"symlink is not allowed: {path}")
    if not path.is_file():
        raise ValueError(f"required file is missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    parent = path.parent
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(parent))
    tmp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o640)
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        tmp = None
        dir_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def repair_active_canonical_ir_project_id(data_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(data_root) if data_root is not None else Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
    selector_path = root / "runtime" / "active-continuation.json"
    selector = _read_object(selector_path)
    if selector.get("schema") != SELECTOR_SCHEMA:
        raise ValueError("unsupported active continuation selector schema")

    project_id = str(selector.get("project_id") or "").strip()
    index_id = str(selector.get("index_id") or "").strip()
    ir_id = str(selector.get("ir_id") or "").strip()
    if project_id != PROJECT_ID:
        raise ValueError("repair is restricted to active agentos-core")
    if not index_id or not ir_id:
        raise ValueError("active selector requires index_id and ir_id")

    project_dir = root / "projects" / project_id
    continuity_dir = project_dir / "continuity"
    execution_path = project_dir / "execution-head.json"
    continuation_path = continuity_dir / "latest.json"
    for path in (project_dir, continuity_dir, execution_path, continuation_path):
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {path}")
    if not project_dir.is_dir() or not continuity_dir.is_dir():
        raise ValueError("canonical project continuity directory is missing")

    lock_path = project_dir / ".continuation-index.lock"
    if lock_path.is_symlink():
        raise ValueError("continuation lock may not be a symlink")

    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o640)
    repaired = False
    try:
        with os.fdopen(lock_fd, "r+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            latest_selector = _read_object(selector_path)
            if any(str(latest_selector.get(key) or "").strip() != value for key, value in (("project_id", project_id), ("index_id", index_id), ("ir_id", ir_id))):
                raise ValueError("active selector changed during repair")

            execution_head = _read_object(execution_path)
            continuation = _read_object(continuation_path)
            canonical_ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else None
            if execution_head.get("schema") != EXECUTION_HEAD_SCHEMA:
                raise ValueError("unsupported execution-head schema")
            if canonical_ir is None or canonical_ir.get("schema_version") != IR_SCHEMA:
                raise ValueError("unsupported canonical IR schema")

            head_index = str(execution_head.get("index_id") or "").strip()
            envelope_index = str(continuation.get("index_id") or "").strip()
            ir_index = str(canonical_ir.get("index_id") or "").strip()
            current_ir_id = str(canonical_ir.get("ir_id") or "").strip()
            if head_index != index_id or envelope_index != index_id or ir_index != index_id or current_ir_id != ir_id:
                raise ValueError("active selector and canonical generation do not match")

            current_project = str(canonical_ir.get("project_id") or "").strip()
            if current_project and current_project != project_id:
                raise ValueError("canonical IR has a conflicting non-empty project_id")
            if not current_project:
                canonical_ir["project_id"] = project_id
                _atomic_write(continuation_path, continuation)
                repaired = True

            verify = _read_object(continuation_path)
            verify_ir = verify.get("canonical_ir") if isinstance(verify.get("canonical_ir"), dict) else {}
            if str(verify_ir.get("project_id") or "").strip() != project_id:
                raise ValueError("canonical IR project_id repair verification failed")
            if str(verify_ir.get("index_id") or "").strip() != index_id or str(verify_ir.get("ir_id") or "").strip() != ir_id:
                raise ValueError("repair changed canonical generation identity")
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    finally:
        pass

    return {
        "schema": "agentos.canonical-ir-project-id-repair/v1",
        "ok": True,
        "repaired": repaired,
        "project_id": project_id,
        "index_id": index_id,
        "ir_id": ir_id,
        "credential_exposed": False,
    }


def main() -> int:
    try:
        result = repair_active_canonical_ir_project_id()
    except Exception as exc:
        print(f"active_canonical_ir_project_id_repair=ERROR {type(exc).__name__}: {exc}")
        return 1
    state = "REPAIRED" if result["repaired"] else "ALREADY_VALID"
    print(f"active_canonical_ir_project_id_repair={state}")
    print("active_canonical_ir_project_id_repair=PASS")
    print(f"active_canonical_ir_project_id_repair_generation={result['project_id']}/{result['index_id']}/{result['ir_id']}")
    print("credential_exposed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
