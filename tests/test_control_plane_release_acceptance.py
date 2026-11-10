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
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if self.path.endswith("/session") else "text/html")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if self.path == "/":
                self.wfile.write("AgentOS 以 Google 登入".encode())
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
