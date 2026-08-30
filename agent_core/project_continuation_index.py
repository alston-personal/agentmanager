from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_core.resolve_facade import resolve_project_identity

PUBLISH_SCHEMA = "agentos.project-continuation-publish/v1"
EXECUTION_HEAD_SCHEMA = "agentos.execution-head/v1"
IR_SCHEMA = "agentos.ir/v1"
INITIAL_PROJECT_ID = "agentos-core"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _assert_plain_path(path: Path, *, allow_missing: bool = False) -> None:
    if path.is_symlink():
        raise ValueError(f"symlink is not allowed: {path}")
    if not path.exists():
        if allow_missing:
            return
        raise ValueError(f"required path is missing: {path}")


def _write_temp(parent: Path, target_name: str, payload: dict[str, Any]) -> Path:
    fd, raw = tempfile.mkstemp(prefix=f".{target_name}.", suffix=".tmp", dir=str(parent))
    tmp = Path(raw)
    try:
        os.fchmod(fd, 0o640)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        return tmp
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        tmp.unlink(missing_ok=True)
        raise


def _index_id_from_continuation(value: dict[str, Any]) -> str:
    direct = str(value.get("index_id") or "").strip()
    canonical_ir = value.get("canonical_ir") if isinstance(value.get("canonical_ir"), dict) else value
    nested = str(canonical_ir.get("index_id") or "").strip()
    if direct and nested and direct != nested:
        raise ValueError("continuation index_id mismatch between envelope and canonical_ir")
    return direct or nested


def validate_publish_params(params: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    if set(params) != {"project_id", "execution_head", "continuation"}:
        raise ValueError("params must contain exactly project_id, execution_head, continuation")
    project_id = str(params.get("project_id") or "").strip()
    if project_id != INITIAL_PROJECT_ID:
        raise ValueError("initial publisher is restricted to agentos-core")
    execution_head = params.get("execution_head")
    continuation = params.get("continuation")
    if not isinstance(execution_head, dict) or not isinstance(continuation, dict):
        raise ValueError("execution_head and continuation must be objects")
    if execution_head.get("schema") != EXECUTION_HEAD_SCHEMA:
        raise ValueError("unsupported execution-head schema")
    canonical_ir = continuation.get("canonical_ir") if isinstance(continuation.get("canonical_ir"), dict) else continuation
    if canonical_ir.get("schema_version") != IR_SCHEMA:
        raise ValueError("continuation must contain agentos.ir/v1 canonical_ir")
    head_index = str(execution_head.get("index_id") or "").strip()
    continuation_index = _index_id_from_continuation(continuation)
    if not head_index or head_index != continuation_index:
        raise ValueError("execution-head and continuation must share one non-empty index_id")
    if not str(canonical_ir.get("ir_id") or "").strip():
        raise ValueError("canonical_ir.ir_id is required")
    if not str(canonical_ir.get("goal") or "").strip():
        raise ValueError("canonical_ir.goal is required")
    recommended = continuation.get("recommended_action")
    nested_continuation = canonical_ir.get("continuation") if isinstance(canonical_ir.get("continuation"), dict) else {}
    if not str(recommended or nested_continuation.get("recommended_action") or nested_continuation.get("next_action") or "").strip():
        raise ValueError("a recommended next action is required")
    return project_id, dict(execution_head), dict(continuation)


def publish_project_continuation(
    params: dict[str, Any],
    *,
    data_root: str | Path | None = None,
    governance_path: str | Path | None = None,
) -> dict[str, Any]:
    project_id, execution_head, continuation = validate_publish_params(params)
    root = Path(data_root) if data_root is not None else Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))

    project = resolve_project_identity(project_id, governance_path=governance_path, data_root=root)
    if project.get("id") != project_id or project.get("identity_source") != "governance-directory":
        raise ValueError("publisher requires canonical governance-directory project identity")
    if not bool((project.get("integrity") or {}).get("mutation_allowed")):
        raise ValueError("canonical project integrity does not permit mutation")

    projects_root = root / "projects"
    project_dir = projects_root / project_id
    _assert_plain_path(projects_root)
    _assert_plain_path(project_dir)
    if project_dir.resolve().parent != projects_root.resolve():
        raise ValueError("project directory escaped canonical projects root")

    continuity_dir = project_dir / "continuity"
    _assert_plain_path(continuity_dir, allow_missing=True)
    continuity_dir.mkdir(mode=0o750, parents=False, exist_ok=True)
    _assert_plain_path(continuity_dir)

    execution_path = project_dir / "execution-head.json"
    continuation_path = continuity_dir / "latest.json"
    _assert_plain_path(execution_path, allow_missing=True)
    _assert_plain_path(continuation_path, allow_missing=True)

    lock_path = project_dir / ".continuation-index.lock"
    if lock_path.is_symlink():
        raise ValueError("continuation lock may not be a symlink")

    index_id = str(execution_head["index_id"])
    execution_head.setdefault("updated_at", _now())
    continuation.setdefault("published_at", _now())

    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o640)
    execution_tmp: Path | None = None
    continuation_tmp: Path | None = None
    try:
        with os.fdopen(lock_fd, "r+") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            execution_tmp = _write_temp(project_dir, execution_path.name, execution_head)
            continuation_tmp = _write_temp(continuity_dir, continuation_path.name, continuation)

            # Publish continuation first and execution-head second. A concurrent
            # resolver uses the shared index_id as a generation fence and will
            # reject/retry any transient mixed pair rather than returning it.
            os.replace(continuation_tmp, continuation_path)
            continuation_tmp = None
            os.replace(execution_tmp, execution_path)
            execution_tmp = None

            for directory in (continuity_dir, project_dir):
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    finally:
        if execution_tmp is not None:
            execution_tmp.unlink(missing_ok=True)
        if continuation_tmp is not None:
            continuation_tmp.unlink(missing_ok=True)

    return {
        "ok": True,
        "schema": PUBLISH_SCHEMA,
        "project_id": project_id,
        "index_id": index_id,
        "execution_head": {
            "path": str(execution_path),
            "sha256": _sha256(execution_head),
            "schema": execution_head.get("schema"),
        },
        "continuation": {
            "path": str(continuation_path),
            "sha256": _sha256(continuation),
            "schema": IR_SCHEMA,
        },
        "authority": {
            "identity_source": project.get("identity_source"),
            "governance_entity_id": project.get("governance_entity_id"),
            "mutation_allowed": True,
        },
        "published_at": _now(),
    }
