from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_action_relay_user.sh"
PUBLISHER = ROOT / "scripts" / "publish_action_relay_capability.py"


def test_installer_uses_fixed_agentos_group_context_for_capability_publish():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "/usr/bin/sg agentos -c" in text
    assert "publish_action_relay_capability.py" in text
    assert "--marker '$CAPABILITY_MARKER'" in text
    assert "--source-ref '$SOURCE_REF'" in text
    assert "--source-commit '$SOURCE_COMMIT'" in text
    assert "action_relay_capability_group_context=PASS" in text


def test_publisher_has_no_generic_execution_surface():
    text = PUBLISHER.read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "shell=True" not in text
    assert "capability_marker_payload" in text
