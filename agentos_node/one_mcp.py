from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

SENSITIVE_KEYS = {
    "token",
    "node_token",
    "access_token",
    "refresh_token",
    "authorization",
    "password",
    "secret",
    "claim_secret",
    "client_secret",
}

ORACLE_LOCAL_MODE = "oracle-local"
CLIENT_MODE = "client"
MAX_LIST_ITEMS = 128
MAX_STRING_LENGTH = 512


class OneGatewayError(RuntimeError):
    """Executor-safe ONE failure containing only a stable classification."""


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if str(key).strip().casefold() in SENSITIVE_KEYS
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, str):
        return value[:MAX_STRING_LENGTH]
    return value


def _bounded_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:MAX_LIST_ITEMS]:
        if isinstance(item, (str, int, float, bool)):
            result.append(str(item)[:256])
    return result


def _project_bootstrap(
    payload: dict[str, Any],
    *,
    schema: str | None = None,
    surface: str = "antigravity",
    executor_class: str | None = None,
    projection: str = "executor-safe-readonly",
) -> dict[str, Any]:
    """Project only executor-orientation fields from a Node/Realm bootstrap."""
    result: dict[str, Any] = {
        "schema": schema or payload.get("schema"),
        "realm_id": payload.get("realm_id"),
        "node_id": payload.get("node_id"),
        "realm_node_count": payload.get("realm_node_count"),
        "realm_capabilities": _bounded_strings(payload.get("realm_capabilities")),
        "inherited_realm_capabilities": _bounded_strings(
            payload.get("inherited_realm_capabilities")
        ),
        "inherited_surface_providers": _bounded_strings(
            payload.get("inherited_surface_providers")
        ),
        "canonical_capabilities": _bounded_strings(
            payload.get("canonical_capabilities")
        ),
        "surface": surface,
        "projection": projection,
        "credential_exposed": False,
    }
    if executor_class:
        result["executor_class"] = executor_class
    return _redact(result)


def _project_execution_head(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    projected = {
        "schema": value.get("schema"),
        "index_id": value.get("index_id"),
        "active_goal": value.get("active_goal"),
    }
    nested = value.get("execution_head")
    if isinstance(nested, dict):
        projected["execution_head"] = {
            key: nested.get(key)
            for key in ("status", "phase", "updated_at")
            if key in nested
        }
    return _redact(projected)


def _project_continuation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    canonical_ir = value.get("canonical_ir")
    if not isinstance(canonical_ir, dict):
        canonical_ir = None
    return _redact(
        {
            "protocol": value.get("protocol"),
            "recommended_action": value.get("recommended_action"),
            "ir_id": value.get("ir_id"),
            "parent_ir_id": value.get("parent_ir_id"),
            "goal": value.get("goal"),
            "constraints": value.get("constraints") or [],
            "decisions": value.get("decisions") or [],
            "pending_tasks": value.get("pending_tasks") or [],
            "continuation": value.get("continuation") or {},
            "capability": value.get("capability"),
            "canonical_ir": canonical_ir,
        }
    )


def _project_resolve(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep continuity state while dropping source paths/runtime manifests."""
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    node_context = payload.get("node_context")
    safe_node_context = None
    if isinstance(node_context, dict):
        safe_node_context = _project_bootstrap(
            node_context,
            schema=node_context.get("schema"),
            surface=str(node_context.get("surface") or "antigravity"),
            executor_class=(
                str(node_context.get("executor_class"))
                if node_context.get("executor_class")
                else None
            ),
            projection="resolve-node-context",
        )
    result = {
        "schema": payload.get("schema"),
        "intent": payload.get("intent"),
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "aliases": _bounded_strings(project.get("aliases")),
            "resolution": project.get("resolution"),
            "matched_by": project.get("matched_by"),
            "identity_source": project.get("identity_source"),
            "governance_entity_id": project.get("governance_entity_id"),
            "governance_state": project.get("governance_state"),
        },
        "mutation_allowed": bool(payload.get("mutation_allowed")),
        "active_goal": payload.get("active_goal"),
        "execution_head": _project_execution_head(payload.get("execution_head")),
        "continuation": _project_continuation(payload.get("continuation")),
        "node_context": safe_node_context,
        "next_action": payload.get("next_action"),
        "availability": payload.get("availability") or {},
        "provenance": payload.get("provenance") or {},
    }
    return _redact(result)


def client_config_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("AGENTOS_CLIENT_CONFIG")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    client_home = os.environ.get("AGENTOS_CLIENT_HOME")
    if client_home:
        candidates.append(Path(client_home).expanduser() / "client.json")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "AgentOS" / "state" / "client.json")
    if os.name == "nt":
        candidates.append(
            Path.home() / "AppData" / "Local" / "AgentOS" / "state" / "client.json"
        )
    candidates.append(Path.home() / ".agentos" / "client.json")

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def discover_client_config() -> Path:
    for path in client_config_candidates():
        if path.is_file():
            return path
    raise FileNotFoundError("agentos_client_config_not_found")


@dataclass(frozen=True)
class ClientConfig:
    one_url: str
    realm_id: str
    node_id: str
    node_token: str

    @classmethod
    def load(cls, path: Path | None = None) -> "ClientConfig":
        source = path or discover_client_config()
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
        required = ("one_url", "realm_id", "node_id", "node_token")
        missing = [key for key in required if not str(payload.get(key) or "").strip()]
        if missing:
            raise ValueError("agentos_client_config_incomplete")
        return cls(
            one_url=str(payload["one_url"]).rstrip("/"),
            realm_id=str(payload["realm_id"]),
            node_id=str(payload["node_id"]),
            node_token=str(payload["node_token"]),
        )


class Gateway(Protocol):
    def status(self) -> dict[str, Any]: ...
    def bootstrap(self) -> dict[str, Any]: ...
    def capabilities(self) -> dict[str, Any]: ...
    def resolve(self, project: str) -> dict[str, Any]: ...
    def probe(self) -> dict[str, Any]: ...


class ClientOneGateway:
    """Credential-isolated read-only adapter from an enrolled client to ONE."""

    mode = CLIENT_MODE

    def __init__(self, config: ClientConfig | None = None):
        self.config = config or ClientConfig.load()

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        authenticated: bool = False,
        timeout: float = 12.0,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "AgentOS-ONE-MCP/0.2"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if authenticated:
            headers["Authorization"] = f"Bearer {self.config.node_token}"
        request = urllib.request.Request(
            self.config.one_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Never read/echo the body; server validation/auth failures can contain
            # secrets, host paths or raw internal state.
            raise OneGatewayError(f"one_http_{int(exc.code)}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OneGatewayError("one_unavailable") from exc
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise OneGatewayError("one_protocol_invalid_json") from exc
        if not isinstance(payload, dict):
            raise OneGatewayError("one_protocol_invalid_shape")
        return _redact(payload)

    def health(self) -> dict[str, Any]:
        return self._request("/v1/health")

    def bootstrap(self) -> dict[str, Any]:
        query = urllib.parse.urlencode({"node_id": self.config.node_id})
        payload = self._request("/v1/bootstrap?" + query, authenticated=True)
        return _project_bootstrap(payload, schema=payload.get("schema"))

    def status(self) -> dict[str, Any]:
        health = self.health()
        bootstrap = self.bootstrap()
        return {
            "schema": "agentos.one-mcp-status/v0.1",
            "connected": bool(health.get("ok"))
            and bootstrap.get("schema") == "agentos.node-bootstrap/v0.1",
            "mode": self.mode,
            "realm_id": bootstrap.get("realm_id") or self.config.realm_id,
            "node_id": bootstrap.get("node_id") or self.config.node_id,
            "surface": "antigravity",
            "adapter": "agentos-one-mcp",
            "credential_boundary": "node credential retained inside local MCP process",
            "credential_exposed": False,
            "realm_node_count": bootstrap.get("realm_node_count"),
        }

    def capabilities(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        return {
            "schema": "agentos.one-mcp-capabilities/v0.1",
            "mode": self.mode,
            "realm_id": bootstrap.get("realm_id"),
            "node_id": bootstrap.get("node_id"),
            "realm_capabilities": bootstrap.get("realm_capabilities") or [],
            "inherited_realm_capabilities": bootstrap.get("inherited_realm_capabilities") or [],
            "inherited_surface_providers": bootstrap.get("inherited_surface_providers") or [],
            "canonical_capabilities": bootstrap.get("canonical_capabilities") or [],
        }

    def resolve(self, project: str) -> dict[str, Any]:
        project = str(project or "").strip()
        if not project:
            raise ValueError("project_required")
        body = {
            "schema": "agentos.resolve-request/v1",
            "intent": "continue",
            "node_id": self.config.node_id,
            "project": project,
        }
        payload = self._request(
            "/v1/resolve",
            method="POST",
            body=body,
            authenticated=True,
        )
        return _project_resolve(payload)

    def probe(self) -> dict[str, Any]:
        result = self.status()
        result["probe"] = "PASS" if result.get("connected") else "FAIL"
        return result


class OracleLocalGateway:
    """Trusted local read-only projection for Oracle-hosted Antigravity.

    This gateway is not a Realm Node and owns no new Realm credential. It runs
    inside the trusted Oracle/ubuntu boundary and exposes only bounded model-
    visible projections of canonical Node Registry / continuation state.
    """

    mode = ORACLE_LOCAL_MODE

    def __init__(self, *, data_root: Path | None = None, core_node_id: str | None = None):
        self.data_root = (
            data_root
            or Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
        ).expanduser()
        self.core_node_id = str(
            core_node_id or os.environ.get("AGENTOS_CORE_NODE_ID", "oracle-core-node")
        ).strip()
        if not self.core_node_id:
            raise ValueError("core_node_id_required")

    def _node_map(self) -> dict[str, Any]:
        from agent_core.node_registry import NodeRegistry

        registry = NodeRegistry(self.data_root / "realm" / "nodes.json")
        return registry.node_map()

    def _core_node(self, node_map: dict[str, Any]) -> dict[str, Any]:
        nodes = list(node_map.get("nodes") or [])
        node = next(
            (
                item
                for item in nodes
                if str(item.get("node_id") or "") == self.core_node_id
            ),
            None,
        )
        if node is None:
            raise KeyError("oracle_core_node_not_registered")
        return node

    def bootstrap(self) -> dict[str, Any]:
        node_map = self._node_map()
        self._core_node(node_map)  # prove membership without exposing raw manifest
        inherited_caps = sorted(
            {
                str(cap)
                for other in (node_map.get("nodes") or [])
                if other.get("node_id") != self.core_node_id
                and other.get("status") != "offline"
                for cap in (other.get("capabilities") or [])
            }
        )
        inherited_surfaces = sorted(
            {
                str(surface.get("provider"))
                for other in (node_map.get("nodes") or [])
                if other.get("node_id") != self.core_node_id
                and other.get("status") != "offline"
                for surface in ((other.get("surface_inventory") or {}).get("surfaces") or [])
                if isinstance(surface, dict) and surface.get("provider")
            }
        )
        raw = {
            "schema": "agentos.one-local-bootstrap/v0.1",
            "realm_id": node_map.get("realm_id"),
            "node_id": self.core_node_id,
            "realm_node_count": node_map.get("node_count", len(node_map.get("nodes") or [])),
            "realm_capabilities": list(node_map.get("realm_capabilities") or []),
            "inherited_realm_capabilities": inherited_caps,
            "inherited_surface_providers": inherited_surfaces,
        }
        return _project_bootstrap(
            raw,
            schema="agentos.one-local-bootstrap/v0.1",
            surface="antigravity",
            executor_class="antigravity-gemini",
            projection="trusted-local-executor-safe",
        )

    def status(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        return {
            "schema": "agentos.one-mcp-status/v0.1",
            "connected": bool(bootstrap.get("realm_id")),
            "mode": self.mode,
            "realm_id": bootstrap.get("realm_id"),
            "node_id": bootstrap.get("node_id"),
            "surface": "antigravity",
            "executor_class": "antigravity-gemini",
            "adapter": "agentos-one-mcp",
            "credential_boundary": (
                "trusted Oracle-local read-only projection; no Realm credential "
                "is exposed to or owned by executor"
            ),
            "credential_exposed": False,
            "realm_node_count": bootstrap.get("realm_node_count"),
        }

    def capabilities(self) -> dict[str, Any]:
        bootstrap = self.bootstrap()
        return {
            "schema": "agentos.one-mcp-capabilities/v0.1",
            "mode": self.mode,
            "realm_id": bootstrap.get("realm_id"),
            "node_id": bootstrap.get("node_id"),
            "realm_capabilities": bootstrap.get("realm_capabilities") or [],
            "inherited_realm_capabilities": bootstrap.get("inherited_realm_capabilities") or [],
            "inherited_surface_providers": bootstrap.get("inherited_surface_providers") or [],
        }

    def resolve(self, project: str) -> dict[str, Any]:
        from agent_core.resolve_facade import resolve_continuation

        project = str(project or "").strip()
        if not project:
            raise ValueError("project_required")
        result = resolve_continuation(
            project,
            data_root=self.data_root,
            node_context=self.bootstrap(),
        )
        return _project_resolve(result)

    def probe(self) -> dict[str, Any]:
        result = self.status()
        result["probe"] = "PASS" if result.get("connected") else "FAIL"
        return result


# Backward-compatible name used by tests and callers written for the first slice.
OneGateway = ClientOneGateway


def gateway_mode() -> str:
    explicit = str(os.environ.get("AGENTOS_ONE_MCP_MODE") or "").strip().casefold()
    if explicit:
        if explicit not in {CLIENT_MODE, ORACLE_LOCAL_MODE}:
            raise ValueError("invalid_one_mcp_mode")
        return explicit
    try:
        discover_client_config()
        return CLIENT_MODE
    except FileNotFoundError:
        pass
    data_root = Path(
        os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
    ).expanduser()
    if os.name != "nt" and (data_root / "realm" / "nodes.json").is_file():
        return ORACLE_LOCAL_MODE
    return CLIENT_MODE


def create_gateway() -> Gateway:
    mode = gateway_mode()
    if mode == ORACLE_LOCAL_MODE:
        return OracleLocalGateway()
    return ClientOneGateway()


def create_mcp_server(gateway: Gateway | None = None):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("mcp_sdk_required") from exc

    one = gateway or create_gateway()
    server = MCPServer("AgentOS ONE")

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
        """Resolve bounded canonical project continuity from ONE."""
        return one.resolve(project)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Credential-isolated AgentOS ONE MCP server")
    parser.add_argument("--probe", action="store_true", help="verify ONE connectivity without starting MCP")
    parser.add_argument(
        "--mode",
        choices=(CLIENT_MODE, ORACLE_LOCAL_MODE),
        help="override gateway mode for this process",
    )
    args = parser.parse_args(argv)
    if args.mode:
        os.environ["AGENTOS_ONE_MCP_MODE"] = args.mode
    if args.probe:
        print(json.dumps(create_gateway().probe(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    create_mcp_server().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
