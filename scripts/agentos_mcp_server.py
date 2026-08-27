#!/usr/bin/env python3
"""Read-only AgentOS MCP server for ChatGPT developer-mode experiments.

Run this on a trusted host and connect it through Secure MCP Tunnel or another
authorized private transport.  Do not expose it anonymously to the public
Internet: the server-side Control Plane credential may authorize private state.
"""

from __future__ import annotations

import os

from mcp.server import MCPServer

from agentos_node.control_plane_client import ControlPlaneClient
from agentos_node.mcp_read_tools import get_project_state, get_task, resume_project


CONTROL_PLANE_URL = os.environ.get("AGENTOS_CONTROL_PLANE_URL", "").strip()
CONTROL_PLANE_TOKEN = os.environ.get("AGENTOS_CONTROL_PLANE_TOKEN")
RUNTIME_ID = os.environ.get("AGENTOS_CHATGPT_RUNTIME_ID", "chatgpt-web").strip() or "chatgpt-web"

if not CONTROL_PLANE_URL:
    raise RuntimeError("AGENTOS_CONTROL_PLANE_URL is required")

client = ControlPlaneClient(CONTROL_PLANE_URL, token=CONTROL_PLANE_TOKEN)
mcp = MCPServer("LeopardCat AgentOS")


@mcp.tool()
def agentos_resume(project_id: str) -> dict:
    """Resume existing AgentOS work before answering a continuation request.

    Use this when the user says continue/resume/繼續, refers to prior project work,
    or expects the current implementation state. Returns authoritative canonical
    state plus compiled execution context; do not substitute chat memory for it.
    This tool is read-only with respect to durable AgentOS task state.
    """

    return resume_project(client, project_id, runtime_id=RUNTIME_ID)


@mcp.tool()
def agentos_project_state(project_id: str) -> dict:
    """Read the current durable AgentOS state for a known project id."""

    return get_project_state(client, project_id)


@mcp.tool()
def agentos_task(task_id: str) -> dict:
    """Read one AgentOS task and its current status by task id."""

    return get_task(client, task_id)


if __name__ == "__main__":
    mcp.run("streamable-http")
