#!/usr/bin/env python3
"""Live Streamable HTTP acceptance probe for the ChatGPT Cloud MCP node.

This proves the actual MCP protocol path, not just TCP readiness or a separate
Control Plane REST request.  The strongest continuity path is:
initialize -> list tools -> resolve active project -> resume -> ONE.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


EXPECTED_TOOLS = {
    "agentos_resolve_active",
    "agentos_resume",
    "agentos_project_state",
    "agentos_task",
}


def _content_text(result: object) -> str:
    content = getattr(result, "content", None) or []
    texts = [getattr(item, "text", "") for item in content if getattr(item, "type", None) == "text"]
    return "\n".join(text for text in texts if text)


def _payload(result: object, tool_name: str) -> dict:
    if getattr(result, "is_error", False):
        raise RuntimeError(f"{tool_name} returned MCP error: {_content_text(result)}")
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    text = _content_text(result)
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{tool_name} result is not JSON/structured content: {text!r}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{tool_name} result root is not an object")
    return payload


async def verify(url: str, fallback_project_id: str) -> None:
    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            missing = EXPECTED_TOOLS - names
            if missing:
                raise RuntimeError(f"missing MCP tools: {sorted(missing)}")

            resolved_result = await session.call_tool("agentos_resolve_active", {"hint": ""})
            resolved = _payload(resolved_result, "agentos_resolve_active")
            if resolved.get("resolution") != "resolved":
                raise RuntimeError(f"bare continuation did not resolve an active project: {resolved!r}")
            project_id = str(resolved.get("project_id") or "").strip()
            if not project_id:
                raise RuntimeError(f"active-project resolver returned no project id: {resolved!r}")

            resume_result = await session.call_tool("agentos_resume", {"project_id": project_id})
            resume = _payload(resume_result, "agentos_resume")
            if resume.get("project_id") != project_id:
                raise RuntimeError(
                    f"resume reached unexpected project: {resume.get('project_id')!r} != {project_id!r}"
                )

            # Keep a known-project read as a secondary regression check.  It proves
            # the historical project-state tool remains usable after adding resolver.
            state_result = await session.call_tool(
                "agentos_project_state", {"project_id": fallback_project_id}
            )
            state = _payload(state_result, "agentos_project_state")
            if state.get("projectId") != fallback_project_id:
                raise RuntimeError(
                    f"project-state tool reached unexpected project: "
                    f"{state.get('projectId')!r} != {fallback_project_id!r}"
                )

            server_info = getattr(initialized, "server_info", None)
            server_name = getattr(server_info, "name", "unknown")
            print("mcp_initialize=ok")
            print(f"mcp_server={server_name}")
            print("mcp_tools=ok")
            print("mcp_resolve_active=ok")
            print(f"mcp_active_project={project_id}")
            print("mcp_resume_active=ok")
            print("mcp_tool_call_one=ok")
            print(f"mcp_project={fallback_project_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--project", default="agentmanager")
    args = parser.parse_args()
    asyncio.run(verify(args.url, args.project))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
