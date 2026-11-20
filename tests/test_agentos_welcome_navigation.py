"""Regression: /welcome must not offer a click-through to itself as 'My AgentOS'."""
from agent_core.companion_web import render_welcome_html


def test_welcome_has_no_misleading_self_link_in_primary_navigation():
    html = render_welcome_html()
    primary = html.split('<nav aria-label="AgentOS 主要導覽"', 1)[1].split("</nav>", 1)[0]
    assert 'href="/welcome"' not in primary
    assert "帳號與 Realm 狀態（目前頁面）" in primary


def test_welcome_header_resolves_to_real_workspace_only_when_authorized():
    html = render_welcome_html()
    assert 'id="agentos-my-entry"' in html
    assert "myEntry.removeAttribute('href')" in html
    assert "myEntry.href = '/platform'" in html
    assert "myEntry.href = '/my-one'" in html
    assert "if (session.role === 'admin')" in html
    assert "data.state === 'realm_initialized'" in html


def test_existing_platform_and_realm_owner_authorization_stays_server_gated():
    # Navigation exposes a route, not an entitlement: the backend still
    # checks /platform and /my-one independently.
    from agent_core.distributed_gateway import DistributedGatewayHandler
    import inspect
    source = inspect.getsource(DistributedGatewayHandler.do_GET)
    assert "account_virtual_one(" in source
    assert 'if code != 200:' in source
