from __future__ import annotations

from typing import Any

from agentos_node.one_mcp import Gateway, create_gateway


def create_server(gateway: Gateway | None = None):
    from mcp.server.mcpserver import MCPServer

    one = gateway or create_gateway()
    server = MCPServer("AgentOS ONE", version="0.1.0")

    @server.tool()
    def one_status() -> dict[str, Any]:
        """Verify this Antigravity executor is connected to AgentOS ONE without exposing credentials."""
        return one.status()

    @server.tool()
    def one_bootstrap() -> dict[str, Any]:
        """Return bounded canonical Realm/Node context available to this Antigravity executor."""
        return one.bootstrap()

    @server.tool()
    def one_capabilities() -> dict[str, Any]:
        """Return canonical/inherited ONE capabilities visible through this adapter."""
        return one.capabilities()

    @server.tool()
    def one_resolve(project: str) -> dict[str, Any]:
        """Resolve project identity, active goal, continuation and mutation boundary from ONE."""
        return one.resolve(project)

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
