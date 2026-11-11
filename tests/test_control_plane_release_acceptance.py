"""Release inspector regression for AgentOS public sign-in and privileged UI."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.inspect_distributed_control_plane import probe


def test_release_inspector_requires_signin_shell_and_oauth_session():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/dashboard/api/auth/session" and self.headers.get("Host") != "agentos.milkcat.org":
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(401 if self.path in ("/v1/account/realm-request", "/v1/platform/realm-requests", "/platform", "/v1/account/virtual-one", "/my-one") else 200)
            self.send_header("Content-Type", "application/json" if self.path.endswith("/session") else "text/html")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if self.path == "/":
                self.wfile.write("AgentOS 以 Google 登入".encode())
            elif self.path == "/welcome":
                from agent_core.companion_web import render_welcome_html
                self.wfile.write(render_welcome_html().encode())
            elif self.path in ("/v1/account/realm-request", "/v1/account/virtual-one", "/my-one"):
                self.wfile.write(json.dumps({"ok": False, "error": "signin_required"}).encode())
            elif self.path == "/v1/platform/realm-requests":
                self.wfile.write(json.dumps({"ok": False, "error": "signin_required"}).encode())
            elif self.path == "/platform":
                self.wfile.write("需要使用已獲授權的平台管理者帳號登入 returnTo=%2Fplatform".encode())
            elif self.path == "/companion":
                self.wfile.write(b"AgentOS Console: Node Map")
            else:
                self.wfile.write(json.dumps({"loggedIn": False, "providers": {"google": True}}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert probe(base + "/", "test-secret", kind="shell")["ok"]
        assert probe(base + "/welcome", "test-secret", kind="welcome")["ok"]
        assert probe(base + "/v1/account/realm-request", "test-secret", kind="account_anon")["ok"]
        assert probe(base + "/v1/account/virtual-one", "test-secret", kind="virtual_one_anon")["ok"]
        assert probe(base + "/my-one", "test-secret", kind="my_one_anon")["ok"]
        assert probe(base + "/v1/platform/realm-requests", "test-secret", kind="platform_anon")["ok"]
        assert probe(base + "/platform", "test-secret", kind="platform_page_anon")["ok"]
        assert probe(base + "/companion", "test-secret", kind="companion")["ok"]
        assert probe(base + "/dashboard/api/auth/session", "test-secret", kind="auth_session")["ok"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_release_inspector_rejects_legacy_root_console_and_broken_auth_session():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if self.path == "/":
                self.wfile.write(b"Node Map")
            else:
                self.wfile.write(json.dumps({"loggedIn": True, "providers": {}}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert not probe(base + "/", "test-secret", kind="shell")["ok"]
        assert not probe(base + "/dashboard/api/auth/session", "test-secret", kind="auth_session")["ok"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_oauth_origin_probe_rejects_studio_and_accepts_agentos():
    from scripts.inspect_distributed_control_plane import probe_oauth_origin
    from urllib.parse import urlsplit

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            provider = urlsplit(self.path).path.rsplit("/", 1)[-1]
            if provider == "facebook":
                target = "https://studio.milkcat.org"
            else:
                target = "https://agentos.milkcat.org"
            callback = target + "/dashboard/api/auth/callback/" + provider
            from urllib.parse import urlencode
            location = "https://example.org/oauth/authorize?" + urlencode({
                "redirect_uri": callback, "state": "12345",
            })
            self.send_response(307)
            self.send_header("Location", location)
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for provider in ("google", "github", "line"):
            receipt = probe_oauth_origin(base, provider, local=True)
            assert receipt["ok"], (provider, receipt)
            assert receipt["agentos_callback"]
        receipt = probe_oauth_origin(base, "facebook", local=True)
        assert receipt["ok"] is False
        assert receipt["agentos_callback"] is False
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_welcome_inspector_rejects_stale_production_copy(monkeypatch):
    import io
    class Response(io.BytesIO):
        def __init__(self, status, body):
            super().__init__(body)
            self.status = status
            self.headers = {}
    old = ('登入狀態；管理者 Console 不會自動開放 ' +
           'id="create-realm" /v1/account/realm-request').encode()
    monkeypatch.setattr('scripts.inspect_distributed_control_plane.urlopen',
                        lambda *a, **k: Response(200, old))
    result = probe('http://test/welcome', 'test-secret', kind='welcome')
    assert result['ok'] is False
    assert result['obsolete_copy_absent'] is False
    assert result['account_header'] is False
