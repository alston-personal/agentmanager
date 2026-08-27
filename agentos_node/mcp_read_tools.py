"""Read-only MCP-facing AgentOS helpers.

These helpers stay independent of any MCP SDK so they can be unit-tested without
pulling transport dependencies into the core test suite. They expose only the
read/attach surface needed for ChatGPT custom-app / developer-mode experiments.
"""

from __future__ import annotations

from typing import Any

from .chatgpt_web_node import bootstrap_chatgpt_web
from .control_plane_client import ControlPlaneClient


def resume_project(
    client: ControlPlaneClient,
    project_id: str,
    *,
    runtime_id: str = "chatgpt-web",
) -> dict[str, Any]:
    """Return the authoritative AgentOS bootstrap packet for one project."""

    return bootstrap_chatgpt_web(client, project_id, runtime_id=runtime_id).to_dict()


def get_project_state(client: ControlPlaneClient, project_id: str) -> dict[str, Any]:
    """Return the current durable project state without constructing new state."""

    return client.get_project_state(project_id)


def get_task(client: ControlPlaneClient, task_id: str) -> dict[str, Any]:
    """Read one AgentOS task by id."""

    return client.get_task(task_id)
