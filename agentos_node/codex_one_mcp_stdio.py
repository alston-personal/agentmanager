from __future__ import annotations

import copy
from typing import Any

from agent_core.active_continuation import resolve_active_continuation
from agentos_node.one_mcp import OracleLocalGateway

SURFACE = "codex-local"
EXECUTOR_CLASS = "openai-codex-local"


def _project_codex_client(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result["surface"] = SURFACE
    result["executor_class"] = EXECUTOR_CLASS
    result["executor_identity_bound"] = True
    result["executor_identity_source"] = "codex-mcp-config"
    result["credential_exposed"] = False
    return result


def _active_projection(one: OracleLocalGateway) -> dict[str, Any]:
    active = resolve_active_continuation(data_root=one.data_root)
    selector = active["selector"]
    resolution = active["resolution"]
    return _project_codex_client(
        {
            "schema": "agentos.one-active-resolve/v1",
            "source": "ONE_ACTIVE_CONTINUATION",
            "selection_source": "ONE_ACTIVE_CONTINUATION",
            "selector": {
                "project_id": selector.get("project_id"),
                "index_id": selector.get("index_id"),
                "ir_id": selector.get("ir_id"),
            },
            "resolution": resolution,
            "credential_exposed": False,
        }
    )


def create_server(gateway: OracleLocalGateway | None = None):
    from mcp.server.mcpserver import MCPServer

    one = gateway or OracleLocalGateway()
    server = MCPServer("AgentOS ONE for Codex", version="0.1.0")

    @server.tool()
    def one_status() -> dict[str, Any]:
        """Verify the Codex local harness can reach the trusted Oracle-local ONE projection."""
        return _project_codex_client(one.status())

    @server.tool()
    def one_capabilities() -> dict[str, Any]:
        """Return bounded ONE capabilities available to the Codex local harness."""
        return _project_codex_client(one.capabilities())

    @server.tool()
    def one_resolve_active() -> dict[str, Any]:
        """Resolve the ONE-selected active Canonical IR; never infer current work from IDE workspace state."""
        return _active_projection(one)

    @server.tool()
    def one_resolve(project: str) -> dict[str, Any]:
        """Explicitly resolve a named canonical project through ONE."""
        return _project_codex_client(one.resolve(project))

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
