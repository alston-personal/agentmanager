"""Read-only MCP-facing AgentOS helpers."""

from __future__ import annotations

from typing import Any

from .chatgpt_web_node import bootstrap_chatgpt_web
from .control_plane_client import ControlPlaneClient


def resume_project(
    client: ControlPlaneClient,
    project_id: str,
    *,
    runtime_id: str = "chatgpt-web",
    principal_id: str | None = None,
) -> dict[str, Any]:
    """Return the authoritative account-scoped AgentOS bootstrap packet."""

    return bootstrap_chatgpt_web(
        client,
        project_id,
        runtime_id=runtime_id,
        principal_id=principal_id,
        transport="mcp",
    ).to_dict()


def get_project_state(client: ControlPlaneClient, project_id: str) -> dict[str, Any]:
    return client.get_project_state(project_id)


def get_task(client: ControlPlaneClient, task_id: str) -> dict[str, Any]:
    return client.get_task(task_id)
