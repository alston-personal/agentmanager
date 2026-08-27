from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "scripts" / "install_chatgpt_secure_mcp_tunnel.sh").read_text(encoding="utf-8")


def test_tunnel_client_release_is_pinned_and_verified():
    assert 'VERSION="v0.0.13"' in INSTALLER
    assert "sha256sum -c -" in INSTALLER
    assert "e71f37b424126513173d5e3590687c0b5ccf6e8ef3fba900104d1f8c60dad906" in INSTALLER
    assert "9d214a805bec213a3a156dc2a4460a6dfe2f35b0c00ba20609d002bf5e6469f8" in INSTALLER
    assert "openai/tunnel-client/releases/download" in INSTALLER


def test_tunnel_is_outbound_only_to_local_mcp():
    assert 'MCP_URL="${AGENTOS_CHATGPT_MCP_URL:-http://127.0.0.1:8000/mcp}"' in INSTALLER
    assert "--mcp.server-url $MCP_URL" in INSTALLER
    assert "--health.listen-addr 127.0.0.1:8781" in INSTALLER
    assert "iptables" not in INSTALLER
    assert "ufw" not in INSTALLER
    assert "nginx" not in INSTALLER


def test_runtime_credentials_are_required_and_admin_key_not_used_by_service():
    assert "blocked_missing_openai_tunnel_id" in INSTALLER
    assert "blocked_missing_openai_tunnel_runtime_key" in INSTALLER
    assert "CONTROL_PLANE_API_KEY=$RUNTIME_KEY" in INSTALLER
    service_block = INSTALLER.split("cat > \"$USER_SYSTEMD_DIR/agentos-chatgpt-openai-tunnel.service\"", 1)[1]
    assert "OPENAI_ADMIN_KEY" not in service_block


def test_tunnel_depends_on_private_chatgpt_mcp_service():
    assert "After=network-online.target agentos-chatgpt-mcp.service" in INSTALLER
    assert "Requires=agentos-chatgpt-mcp.service" in INSTALLER
    assert "openai_tunnel_ready=ok" in INSTALLER
