#!/usr/bin/env python3
"""Live Streamable HTTP acceptance probe for the ChatGPT Cloud MCP node.

This proves the actual MCP protocol path, not just TCP readiness or a separate
Control Plane REST request: initialize -> list tools -> call AgentOS tool -> ONE.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


EXPECTED_TOOLS = {"agentos_resume", "agentos_project_state", "agentos_task"}


def _content_text(result: object) -> str:
    content = getattr(result, "content", None) or []
    texts = [getattr(item, "text", "") for item in content if getattr(item, "type", None) == "text"]
    return "\n".join(text for text in texts if text)


async def verify(url: str, project_id: str) -> None:
    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            missing = EXPECTED_TOOLS - names
            if missing:
                raise RuntimeError(f"missing MCP tools: {sorted(missing)}")

            result = await session.call_tool("agentos_project_state", {"project_id": project_id})
            if getattr(result, "is_error", False):
                raise RuntimeError(f"agentos_project_state returned MCP error: {_content_text(result)}")

            structured = getattr(result, "structured_content", None)
            payload = structured if isinstance(structured, dict) else None
            if payload is None:
                text = _content_text(result)
                try:
                    payload = json.loads(text)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"MCP tool result is not JSON/structured content: {text!r}") from exc

            if payload.get("projectId") != project_id:
                raise RuntimeError(
                    f"MCP tool reached unexpected project: {payload.get('projectId')!r} != {project_id!r}"
                )

            server_info = getattr(initialized, "server_info", None)
            server_name = getattr(server_info, "name", "unknown")
            print("mcp_initialize=ok")
            print(f"mcp_server={server_name}")
            print("mcp_tools=ok")
            print("mcp_tool_call_one=ok")
            print(f"mcp_project={project_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--project", default="agentmanager")
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
