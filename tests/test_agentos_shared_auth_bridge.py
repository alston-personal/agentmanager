from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

import agent_core.shared_auth_bridge as bridge


def test_auth_route_allowlist_and_host_isolation(tmp_path: Path):
    assert bridge.is_shared_auth_path("/dashboard/api/auth/signin/google")
    assert bridge.is_shared_auth_path("/dashboard/api/auth/callback/github")
    assert bridge.is_shared_auth_path("/dashboard/api/auth/signin/facebook")
    assert bridge.is_shared_auth_path("/dashboard/api/auth/callback/facebook")
    assert bridge.is_shared_auth_path("/dashboard/api/auth/signin/line")
    assert bridge.is_shared_auth_path("/dashboard/api/auth/callback/line")
    assert bridge.is_shared_auth_path("/dashboard/api/auth/session")
    for path in (
        "/dashboard/api/auth/login", "/dashboard/api/auth/pwa/start",
        "/dashboard/api/agentos/v1/tasks", "/dashboard/api/auth/signin/evil",
        "/dashboard/api/auth/callback/github/../../projects",
    ):
        assert not bridge.is_shared_auth_path(path)
        assert bridge.proxy_shared_auth_request(
            raw_path=path, method="GET", host="agentos.milkcat.org"
        )[0] == 404
    assert bridge.proxy_shared_auth_request(
        raw_path="/dashboard/api/auth/session", method="GET",
        host="studio.milkcat.org",
    )[0] == 400
    assert bridge.proxy_shared_auth_request(
        raw_path="/dashboard/api/auth/session", method="POST",
        host="agentos.milkcat.org",
    )[0] == 404
    state = tmp_path / "active-port"
    state.write_text("9999")
    with pytest.raises(ValueError, match="invalid active"):
        bridge.resolve_dashboard_port(state)


def test_proxy_preserves_oauth_redirect_and_multiple_cookies(tmp_path: Path, monkeypatch):
    calls = []

    class AuthStub(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get("Host"),
                          self.headers.get("Cookie"), self.headers.get("Authorization"),
                          self.headers.get("X-Forwarded-Host"), self.headers.get("X-Forwarded-Proto")))
            self.send_response(302)
            self.send_header("Location", "https://agentos.milkcat.org/")
            self.send_header("Set-Cookie", "auth_token=one; Path=/; HttpOnly")
            self.send_header("Set-Cookie", "oauth_return_to=; Path=/; Max-Age=0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), AuthStub)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state = tmp_path / "active-port"
    state.write_text(str(server.server_port))
    monkeypatch.setattr(bridge, "AUTHORIZED_PORTS", {server.server_port})
    try:
        status, headers, body = bridge.proxy_shared_auth_request(
            raw_path="/dashboard/api/auth/callback/google?code=x&state=y",
            method="GET", host="agentos.milkcat.org",
            cookie="oauth_return_to=test",
            state_file=state,
        )
        assert status == 302 and body == b""
        assert [v for k, v in headers if k.lower() == "set-cookie"] == [
            "auth_token=one; Path=/; HttpOnly",
            "oauth_return_to=; Path=/; Max-Age=0",
        ]
        assert calls == [(
            "/dashboard/api/auth/callback/google?code=x&state=y",
            "agentos.milkcat.org", "oauth_return_to=test", None,
            "agentos.milkcat.org", "https",
        )]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
