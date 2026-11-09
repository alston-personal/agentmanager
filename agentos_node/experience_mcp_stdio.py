from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agent_core.experience import ExperienceQuery
from agent_core.experience_runtime import prehydrate_experience
from agent_core.experience_store import discover_from_one

SURFACE = "codex-local"
EXECUTOR_CLASS = "openai-codex-local"


def _data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT", os.environ.get("AGENTOS_DATA_ROOT", "/home/ubuntu/agent-data"))).expanduser()


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
    return prehydrate_experience(
        project_id=project_id,
        active_goal=active_goal,
        realm=realm or None,
        capabilities=tuple(capabilities or ()),
        executor=executor or None,
        limit=limit,
        surface=SURFACE,
        executor_class=EXECUTOR_CLASS,
        data_root=_data_root(),
    )


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
