from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_control_inbox_bridge_user.sh"
AUTH_REPAIR = ROOT / "scripts" / "repair_control_inbox_github_auth_user.sh"
BOOTSTRAP = ROOT / "agentos_node" / "bootstrap_control.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_installer_is_exact_integration_generation_and_enables_identity_only_continuation():
    text = _text(INSTALLER)
    assert 'SOURCE_REF="${AGENTOS_REF:-core/integration}"' in text
    assert 'EXPECTED_SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"' in text
    assert 'core/integration)' in text
    assert 'git -C "$REPO" fetch --no-tags origin "$EXPECTED_SOURCE_COMMIT"' in text
    assert 'merge-base --is-ancestor "$SOURCE_COMMIT" "$LANE_HEAD"' in text
    assert 'AGENTOS_CONTROL_ALLOWED_ACTIONS=$ALLOWED_ACTIONS' in text
    assert 'agentos.continuation.inspect' in text
    assert 'control_inbox_continuation_identity=ENABLED' in text
    assert 'control_inbox_exact_generation=PASS' in text
    assert 'canonical_ir' not in text.lower()


def test_auth_repair_rebuilds_same_fixed_action_allowlist():
    text = _text(AUTH_REPAIR)
    expected = 'agent.surface.inspect,desktop.session.inspect,desktop.windows.inspect,agentos.continuation.inspect'
    assert f'ALLOWED_ACTIONS="{expected}"' in text
    assert 'AGENTOS_CONTROL_ALLOWED_ACTIONS=$ALLOWED_ACTIONS' in text
    assert 'Exactly eleven fixed KEY=VALUE lines' in text
    assert 'control_inbox_continuation_identity=ENABLED' in text


def test_bootstrap_reconcile_is_fixed_exact_generation_action():
    text = _text(BOOTSTRAP)
    assert 'ACTION_RECONCILE_CONTROL_INBOX = "agentos.control_inbox.reconcile"' in text
    assert 'ACTION_RECONCILE_CONTROL_INBOX,' in text
    assert 'ACTION_RECONCILE_CONTROL_INBOX,' in text.split('exact_actions = {', 1)[1]
    section = text.split('if action == ACTION_RECONCILE_CONTROL_INBOX:', 1)[1].split('if action == ACTION_DEPLOY_REALM_GATEWAY:', 1)[0]
    assert '"scripts/install_control_inbox_bridge_user.sh"' in section
    assert 'env_extra={"AGENTOS_REF": "core/integration"}' in section
    assert 'source_commit=source_commit' in section
    assert 'arbitrary_shell' in text
    assert 'unknown = set(params) - {"source_commit"}' in text
