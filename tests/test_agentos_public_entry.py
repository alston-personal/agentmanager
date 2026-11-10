from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent_core.companion_web import render_public_entry_html
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService


def test_public_entry_has_login_not_operator_token():
    html = render_public_entry_html()
    assert 'site=agentos' in html
    assert '/dashboard/api/auth/signin/google' in html
    assert '/dashboard/api/auth/signin/github' in html
    assert "window.prompt(" not in html
    assert "agentos_operator_token" not in html
    assert "Approve Node Join" not in html


def test_gateway_public_home_is_separate_from_privileged_companion(tmp_path: Path):
    store = DistributedControlPlane(tmp_path / "gateway.sqlite3")
    server = DistributedGatewayServer(
        ("127.0.0.1", 0), DistributedGatewayService(store), token="test-root-secret"
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for method in ("GET", "HEAD"):
            with urlopen(Request(base + "/", method=method), timeout=3) as response:
                assert response.status == 200
                assert response.headers["Cache-Control"] == "no-store"
                if method == "GET":
                    html = response.read().decode("utf-8")
                    assert "以 Google 登入" in html
                    assert "AgentOS operator token (stored only on this device)" not in html
        with urlopen(base + "/companion", timeout=3) as response:
            assert b"AgentOS Console" in response.read()
        try:
            urlopen(base + "/v1/approvals", timeout=3)
            assert False, "anonymous must never access operator approvals"
        except HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
