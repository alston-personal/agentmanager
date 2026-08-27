"""Read-only MCP-facing AgentOS helpers."""

from __future__ import annotations

from typing import Any

from .chatgpt_web_node import bootstrap_chatgpt_web
from .control_plane_client import ControlPlaneClient


def resolve_active_project(client: ControlPlaneClient, *, hint: str | None = None) -> dict[str, Any]:
    """Resolve the authoritative active readable project from ONE."""

    return client.resolve_active_project(hint=hint)


def resume_project(
    client: ControlPlaneClient,
    project_id: str,
    *,
    runtime_id: str = "chatgpt-web",
    principal_id: str | None = None,
    transport: str = "mcp",
) -> dict[str, Any]:
    """Return the authoritative account-scoped AgentOS bootstrap packet."""

    return bootstrap_chatgpt_web(
        client,
        project_id,
        runtime_id=runtime_id,
        principal_id=principal_id,
        transport=transport,
    ).to_dict()


def get_project_state(client: ControlPlaneClient, project_id: str) -> dict[str, Any]:
    return client.get_project_state(project_id)


def get_task(client: ControlPlaneClient, task_id: str) -> dict[str, Any]:
    return client.get_task(task_id)
