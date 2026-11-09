from pathlib import Path

onboarding=Path('agentos_node/onboarding.py').read_text(encoding='utf-8')
cli=Path('agentos_node/client_cli.py').read_text(encoding='utf-8')
installer=Path('scripts/install_thin_client_macos.sh').read_text(encoding='utf-8')

def test_macos_supervisor_contract():
    assert "MACOS_LAUNCH_AGENT_LABEL = 'org.milkcat.agentos.thin-client'" in onboarding
    assert "launchctl','bootstrap'" in onboarding
    assert "launchctl','kickstart'" in onboarding
    assert "KeepAlive" in onboarding
    assert "RunAtLoad" in onboarding

def test_client_cli_uses_cross_platform_supervisor():
    assert "install_node_supervisor()" in cli
    assert "check_node_supervisor()" in cli
    assert "install_windows_node_supervisor()" not in cli

def test_macos_installer_contract():
    assert 'https://studio.milkcat.org/dashboard/api/agentos' in installer
    assert 'AGENTOS_NODE_ID:-mbpr' in installer
    assert 'agentos-client' in installer
    assert 'policy-init' in installer
    assert 'join --one' in installer
    assert 'install_macos_node_supervisor' in installer

# trigger macOS contract guard
