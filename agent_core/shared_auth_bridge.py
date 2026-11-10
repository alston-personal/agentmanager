"""Fixed, read-only-configured proxy from the AgentOS Console to shared OAuth.

This deliberately cannot proxy arbitrary URLs or user-chosen ports. It is
only a transport bridge: a successful OAuth session does NOT grant ONE,
operator, or Realm permissions.
"""
from __future__ import annotations

from http.client import HTTPConnection
from pathlib import Path
import re
from urllib.parse import urlsplit

BLUE_GREEN_ACTIVE_PORT = Path("/home/ubuntu/agent-data/runtime/dashboard-blue-green/active-port")
AUTHORIZED_PORTS = {3000, 3040, 3041}
AUTHORIZED_HOST = "agentos.milkcat.org"
_ALLOWED_AUTH_ROUTES = re.compile(
    r"/dashboard/api/auth/(?:signin/(?:google|github|facebook|line)|callback/(?:google|github)|session|logout)/?\Z"
)
_ALLOWED_RESPONSE_HEADERS = {"content-type", "location", "set-cookie", "cache-control", "vary"}


def is_shared_auth_path(path: str) -> bool:
    return _ALLOWED_AUTH_ROUTES.fullmatch(path) is not None


def resolve_dashboard_port(state_file: Path = BLUE_GREEN_ACTIVE_PORT) -> int:
    if not state_file.exists():
        # Match the documented pre-blue-green Dashboard deployment.
        return 3000
    port = int(state_file.read_text(encoding="ascii").strip())
    if port not in AUTHORIZED_PORTS or port == 3000:
        raise ValueError("invalid active blue-green port")
    return port


def proxy_shared_auth_request(
    *,
    raw_path: str,
    method: str,
    host: str,
    cookie: str | None = None,
    state_file: Path = BLUE_GREEN_ACTIVE_PORT,
) -> tuple[int, list[tuple[str, str]], bytes]:
    parsed = urlsplit(raw_path)
    if not is_shared_auth_path(parsed.path) or method not in {"GET", "HEAD"}:
        return 404, [("Content-Type", "application/json")], b'{"error":"not_found"}'
    # A request arriving with any other Host is not an AgentOS authentication
    # request. Never honor X-Forwarded-Host from a browser.
    if host.lower().split(":")[0] != AUTHORIZED_HOST:
        return 400, [("Content-Type", "application/json")], b'{"error":"invalid_auth_host"}'

    port = resolve_dashboard_port(state_file)
    headers = {"Host": AUTHORIZED_HOST, "Accept": "application/json, text/html;q=0.9"}
    if cookie:
        headers["Cookie"] = cookie[:8192]
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, parsed.path + (("?" + parsed.query) if parsed.query else ""), headers=headers)
        resp = conn.getresponse()
        body = resp.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("auth upstream body exceeds limit")
        forwarded_headers = [(key, value) for key, value in resp.getheaders()
                             if key.lower() in _ALLOWED_RESPONSE_HEADERS]
        # Preserve every Set-Cookie independently, never fold them into one.
        return resp.status, forwarded_headers, body
    finally:
        conn.close()
