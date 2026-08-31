import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).strip().casefold() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


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
        candidates.append(Path.home() / "AppData" / "Local" / "AgentOS" / "state" / "client.json")
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
    searched = ", ".join(str(path) for path in client_config_candidates())
    raise FileNotFoundError(
        "AgentOS client.json not found. Set AGENTOS_CLIENT_CONFIG or AGENTOS_CLIENT_HOME. "
        f"Searched: {searched}"
    )


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
            raise ValueError(f"AgentOS client config missing fields: {missing}")
        return cls(
            one_url=str(payload["one_url"]).rstrip("/"),
            realm_id=str(payload["realm_id"]),
            node_id=str(payload["node_id"]),
            node_token=str(payload["node_token"]),
        )


class OneGateway:
    """Credential-isolated read-only adapter from Antigravity MCP to ONE."""

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
        headers = {
            "Accept": "application/json",
            "User-Agent": "AgentOS-ONE-MCP/0.1",
        }
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
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ONE HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"ONE connection failed: {exc.reason}") from exc
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            raise RuntimeError("ONE response must be a JSON object")
        return _redact(payload)

    def health(self) -> dict[str, Any]:
        return self._request("/v1/health")

    def bootstrap(self) -> dict[str, Any]:
        query = urllib.parse.urlencode({"node_id": self.config.node_id})
        return self._request("/v1/bootstrap?" + query, authenticated=True)

    def status(self) -> dict[str, Any]:
        health = self.health()
        bootstrap = self.bootstrap()
        return {
            "schema": "agentos.one-mcp-status/v0.1",
            "connected": bool(health.get("ok"))
            and bootstrap.get("schema") == "agentos.node-bootstrap/v0.1",
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
            raise ValueError("project is required")
        body = {
            "schema": "agentos.resolve-request/v1",
            "intent": "continue",
            "node_id": self.config.node_id,
            "project": project,
        }
        return self._request(
            "/v1/resolve",
            method="POST",
            body=body,
            authenticated=True,
        )

    def probe(self) -> dict[str, Any]:
        result = self.status()
        result["probe"] = "PASS" if result.get("connected") else "FAIL"
        return result


def create_mcp_server(gateway: OneGateway | None = None):
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "MCP Python SDK v2 is required. Run scripts/install_antigravity_one_mcp.py first."
        ) from exc

    one = gateway or OneGateway()
    server = MCPServer("AgentOS ONE")

    @server.tool()
    def one_status() -> dict[str, Any]:
        """Verify this Antigravity executor is connected to AgentOS ONE without exposing credentials."""
        return one.status()

    @server.tool()
    def one_bootstrap() -> dict[str, Any]:
        """Return canonical Realm/Node bootstrap context available to this enrolled AgentOS client."""
        return one.bootstrap()

    @server.tool()
    def one_capabilities() -> dict[str, Any]:
        """Return canonical and inherited ONE capabilities visible to this Node."""
        return one.capabilities()

    @server.tool()
    def one_resolve(project: str) -> dict[str, Any]:
        """Resolve project identity, active goal, continuation and mutation boundary from ONE."""
        return one.resolve(project)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Credential-isolated AgentOS ONE MCP server")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="verify ONE connectivity without starting MCP",
    )
    args = parser.parse_args(argv)
    if args.probe:
        print(json.dumps(OneGateway().probe(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    create_mcp_server().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
