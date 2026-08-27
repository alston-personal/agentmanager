#!/usr/bin/env python3
"""Remote read-only AgentOS MCP server for an account-scoped ChatGPT node.

This is the preferred cross-device transport. ChatGPT connects to the remote MCP
server; the server attaches to ONE and restores canonical state. No device,
browser profile, or conversation id participates in durable node identity.

The MCP process MUST use a scoped AgentOS client token, never the ONE root bearer.
"""

from __future__ import annotations

import os

from mcp.server import MCPServer

from agentos_node.control_plane_client import ControlPlaneClient
from agentos_node.mcp_read_tools import get_project_state, get_task, resume_project


CONTROL_PLANE_URL = os.environ.get("AGENTOS_CONTROL_PLANE_URL", "").strip()
CHATGPT_CLIENT_TOKEN = os.environ.get("AGENTOS_CHATGPT_CLIENT_TOKEN", "").strip()
RUNTIME_ID = os.environ.get("AGENTOS_CHATGPT_RUNTIME_ID", "chatgpt-web").strip() or "chatgpt-web"
PRINCIPAL_ID = os.environ.get("AGENTOS_CHATGPT_PRINCIPAL_ID", "").strip() or None
MCP_HOST = os.environ.get("AGENTOS_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
MCP_PORT = int(os.environ.get("AGENTOS_MCP_PORT", "8000"))
MCP_PATH = os.environ.get("AGENTOS_MCP_PATH", "/mcp").strip() or "/mcp"

if not CONTROL_PLANE_URL:
    raise RuntimeError("AGENTOS_CONTROL_PLANE_URL is required")
if not CHATGPT_CLIENT_TOKEN:
    raise RuntimeError("AGENTOS_CHATGPT_CLIENT_TOKEN is required; do not use the ONE root token")

client = ControlPlaneClient(CONTROL_PLANE_URL, token=CHATGPT_CLIENT_TOKEN)
mcp = MCPServer(
    "LeopardCat AgentOS",
    instructions=(
        "AgentOS is authoritative for existing work. For continuation requests, "
        "call agentos_resume before using conversational memory. This ChatGPT node "
        "is account-scoped and must behave identically across devices."
    ),
)


@mcp.tool()
def agentos_resume(project_id: str) -> dict:
    """Restore an existing AgentOS project before answering continuation intent."""
    return resume_project(
        client,
        project_id,
        runtime_id=RUNTIME_ID,
        principal_id=PRINCIPAL_ID,
    )


@mcp.tool()
def agentos_project_state(project_id: str) -> dict:
    """Read current durable AgentOS state for a known project."""
    return get_project_state(client, project_id)


@mcp.tool()
def agentos_task(task_id: str) -> dict:
    """Read one AgentOS task and status by id."""
    return get_task(client, task_id)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        json_response=True,
    )
