"""Executor-neutral ONE Experience prehydration runtime.

The Master Experience Floor is an AgentOS responsibility. This module owns the
bounded pre-executor hydration + receipt semantics so executor launch paths do
not depend on an MCP transport module. MCP surfaces may delegate here, but the
minimum floor remains available even when no MCP server is imported or started.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from agent_core.experience_store import hydrate_from_one

RECEIPT_SCHEMA = "agentos.experience-hydration-receipt/v1"


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", os.environ.get("AGENTOS_DATA_ROOT", "/home/ubuntu/agent-data"))).expanduser()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_commit() -> str:
    explicit = str(os.environ.get("AGENTOS_RUNTIME_SOURCE_COMMIT") or "").strip()
    if explicit:
        return explicit
    return Path(__file__).resolve().parents[1].name


def _receipt_path(data_root: Path) -> Path:
    return Path(
        os.environ.get(
            "AGENTOS_EXPERIENCE_HYDRATION_RECEIPT",
            str(data_root / "runtime" / "experience-hydration-last.json"),
        )
    ).expanduser()


def _write_receipt(
    projection: dict[str, Any],
    *,
    data_root: Path,
    surface: str,
    executor_class: str,
) -> None:
    path = _receipt_path(data_root)
    if path.is_symlink():
        raise ValueError("Experience hydration receipt path must not be a symlink")
    payload = {
        "schema": RECEIPT_SCHEMA,
        "recorded_at": _utc_now(),
        "runtime_source_commit": _source_commit(),
        "source": projection.get("source"),
        "surface": surface,
        "executor_class": executor_class,
        "executor_identity_bound": True,
        "project_id": projection.get("project_id"),
        "projection_digest": projection.get("digest"),
        "experience_ids": list(projection.get("experience_ids") or []),
        "credential_exposed": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o640)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def prehydrate_experience(
    *,
    project_id: str,
    active_goal: str,
    realm: str | None,
    capabilities: tuple[str, ...] = (),
    executor: str | None,
    surface: str,
    executor_class: str,
    limit: int = 20,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Resolve ONE Experience and record an independent bounded receipt."""
    root = data_root or _data_root()
    projection = hydrate_from_one(
        project_id=project_id,
        active_goal=active_goal,
        realm=realm,
        capabilities=capabilities,
        executor=executor,
        limit=limit,
        data_root=root,
    )
    projection["surface"] = surface
    projection["executor_class"] = executor_class
    projection["executor_identity_bound"] = True
    projection["credential_exposed"] = False
    _write_receipt(
        projection,
        data_root=root,
        surface=surface,
        executor_class=executor_class,
    )
    return projection
