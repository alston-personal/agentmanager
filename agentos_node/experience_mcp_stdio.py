from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from agent_core.experience import ExperienceQuery
from agent_core.experience_store import discover_from_one, hydrate_from_one

SURFACE = "codex-local"
EXECUTOR_CLASS = "openai-codex-local"
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


def _receipt_path() -> Path:
    return Path(
        os.environ.get(
            "AGENTOS_EXPERIENCE_HYDRATION_RECEIPT",
            str(_data_root() / "runtime" / "experience-hydration-last.json"),
        )
    ).expanduser()


def _write_receipt(projection: dict[str, Any]) -> None:
    path = _receipt_path()
    if path.is_symlink():
        raise ValueError("Experience hydration receipt path must not be a symlink")
    payload = {
        "schema": RECEIPT_SCHEMA,
        "recorded_at": _utc_now(),
        "runtime_source_commit": _source_commit(),
        "source": projection.get("source"),
        "surface": SURFACE,
        "executor_class": EXECUTOR_CLASS,
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


def _project(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "agentos.experience-discovery/v1",
        "source": "ONE_EXPERIENCE",
        "surface": SURFACE,
        "executor_class": EXECUTOR_CLASS,
        "executor_identity_bound": True,
        "experience_ids": [item.get("experience_id") for item in items],
        "items": items,
        "credential_exposed": False,
    }


def one_experience_discover(
    project_id: str,
    realm: str = "oracle",
    capabilities: list[str] | None = None,
    executor: str = "codex",
    limit: int = 20,
) -> dict[str, Any]:
    items = discover_from_one(
        ExperienceQuery(
            project_id=project_id,
            realm=realm or None,
            capabilities=tuple(capabilities or ()),
            executor=executor or None,
            limit=limit,
        ),
        data_root=_data_root(),
    )
    return _project(items)


def one_experience_hydrate(
    project_id: str,
    active_goal: str,
    realm: str = "oracle",
    capabilities: list[str] | None = None,
    executor: str = "codex",
    limit: int = 20,
) -> dict[str, Any]:
    projection = hydrate_from_one(
        project_id=project_id,
        active_goal=active_goal,
        realm=realm or None,
        capabilities=tuple(capabilities or ()),
        executor=executor or None,
        limit=limit,
        data_root=_data_root(),
    )
    projection["surface"] = SURFACE
    projection["executor_class"] = EXECUTOR_CLASS
    projection["executor_identity_bound"] = True
    projection["credential_exposed"] = False
    _write_receipt(projection)
    return projection


def create_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("AgentOS ONE Experience", version="0.1.0")
    server.tool()(one_experience_discover)
    server.tool()(one_experience_hydrate)
    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
