from __future__ import annotations

import copy
from typing import Any

from agent_core.historical_ir import discover_historical_irs
from agentos_node.one_mcp import Gateway, create_gateway
from agentos_node.one_runtime_inspect import inspect_oracle_runtime


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


def _runtime_inspect(one: Gateway) -> dict[str, Any]:
    if str(getattr(one, "mode", "")) != "oracle-local":
        return {
            "schema": "agentos.one-runtime-inspect/v0.1",
            "mode": str(getattr(one, "mode", "unknown")),
            "supported": False,
            "reason": "oracle_local_only",
            "credential_exposed": False,
            "mutation_allowed": False,
        }
    return inspect_oracle_runtime(
        data_root=getattr(one, "data_root", None),
        core_node_id=getattr(one, "core_node_id", None),
    )


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

    @server.tool()
    def one_historical_ir_discover(project_id: str, limit: int = 50) -> dict[str, Any]:
        """List bounded Historical IR metadata for review; it never changes active continuation."""
        return _unbind_executor_identity({
            "schema": "agentos.historical-ir-discovery/v1",
            "source": "ONE_HISTORICAL_IR",
            "project_id": project_id,
            "items": discover_historical_irs(project_id, data_root=getattr(one, "data_root", None), limit=limit),
            "active_ir_mutated": False,
            "credential_exposed": False,
        })

    @server.tool()
    def one_runtime_inspect() -> dict[str, Any]:
        """Return fixed, sanitized Oracle runtime facts; accepts no command, path, unit, or credential input."""
        return _unbind_executor_identity(_runtime_inspect(one))

    return server


def main() -> int:
    create_server().run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
