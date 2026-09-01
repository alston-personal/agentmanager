from __future__ import annotations

import copy
from typing import Any

from agentos_node.one_mcp import Gateway, create_gateway


def _unbind_executor_identity(value: dict[str, Any]) -> dict[str, Any]:
    """Return an MCP projection that never guesses the caller executor.

    The stdio MCP process is shared by the Antigravity surface and receives no
    reliable per-tool caller model identity.  Only the PreInvocation hook has
    modelName context, so MCP may prove ONE/surface connectivity but not whether
    the current caller is Gemini, Codex, or another executor.
    """
    result = copy.deepcopy(value)

    def mark_unbound(target: Any) -> None:
        if not isinstance(target, dict):
            return
        if "executor_class" in target:
            target["executor_class"] = "antigravity-unbound"
        target["executor_identity_bound"] = False
        target["executor_identity_source"] = "preinvocation-hook-required"

    mark_unbound(result)
    mark_unbound(result.get("node_context"))
    return result


def create_server(gateway: Gateway | None = None):
    from mcp.server.mcpserver import MCPServer

    one = gateway or create_gateway()
    server = MCPServer("AgentOS ONE", version="0.1.0")

    @server.tool()
    def one_status() -> dict[str, Any]:
        """Verify the Antigravity surface is connected to AgentOS ONE without exposing credentials."""
        return _unbind_executor_identity(one.status())

    @server.tool()
    def one_bootstrap() -> dict[str, Any]:
        """Return bounded canonical Realm/Node context without guessing caller executor identity."""
        return _unbind_executor_identity(one.bootstrap())

    @server.tool()
    def one_capabilities() -> dict[str, Any]:
        """Return canonical/inherited ONE capabilities visible through this adapter."""
        return _unbind_executor_identity(one.capabilities())

    @server.tool()
    def one_resolve(project: str) -> dict[str, Any]:
        """Resolve project identity, active goal, continuation and mutation boundary from ONE."""
        return _unbind_executor_identity(one.resolve(project))

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
