from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent_core.companion_web import render_public_entry_html, render_welcome_html
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService


def test_public_entry_has_login_not_operator_token():
    html = render_public_entry_html()
    welcome = render_welcome_html()
    assert 'id="agentos-account-identity"' in welcome
    assert 'session.username' in welcome
    assert 'session.role' in welcome
    assert 'href="/dashboard/api/auth/logout?returnTo=%2F"' in welcome
    assert 'id="agentos-admin-entry"' in welcome
    assert 'innerHTML' not in welcome
    assert 'site=agentos' in html
    assert html.count('returnTo=%2Fwelcome') == 4
    assert render_welcome_html().count('dashboard/api/auth/session') == 2
    assert '/dashboard/api/auth/signin/google' in html
    assert '/dashboard/api/auth/signin/github' in html
    assert '/dashboard/api/auth/signin/facebook' in html
    assert '/dashboard/api/auth/signin/line' in html
    assert html.count('site=agentos') == 4
    assert "window.prompt(" not in html
    assert "agentos_operator_token" not in html
    assert "Approve Node Join" not in html
    assert "agentos_operator_token" not in html
    assert "AgentOS Console" not in html


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
        with urlopen(base + "/welcome", timeout=3) as response:
            welcome = response.read().decode("utf-8")
            assert response.status == 200
            assert "登入狀態" in welcome
            assert "平台管理員工作區" in welcome
            assert "session.role === 'admin'" in welcome
            assert 'id="platform-admin-link"' in welcome
            assert "此帳號尚未取得平台管理權限" in welcome
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
