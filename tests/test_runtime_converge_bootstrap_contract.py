from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP = ROOT / "scripts" / "bootstrap_runtime_converger_oracle.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy-agentos-core.yml"


def test_bootstrap_is_exact_ref_exact_sha_and_clean_tree_only():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'SOURCE_REF="${1:-}"' in text
    assert 'SOURCE_COMMIT="${2:-}"' in text
    assert '[ "$SOURCE_REF" != "core/integration" ]' in text
    assert "^[0-9a-f]{40}$" in text
    assert 'git status --porcelain --untracked-files=no' in text
    assert 'CURRENT="$(git rev-parse HEAD)"' in text
    assert 'FETCHED="$(git rev-parse FETCH_HEAD)"' in text
    assert '[ "$FETCHED" != "$SOURCE_COMMIT" ]' in text


def test_bootstrap_uses_fixed_installers_and_verifies_installed_marker():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert 'AGENTOS_ACTION_SOURCE_REF="$SOURCE_REF"' in text
    assert 'AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT"' in text
    assert "bash scripts/install_action_relay_user.sh" in text
    assert "agentos.action-relay-capabilities/v1" in text
    assert 'bash scripts/install_realm_fabric_user.sh' in text
    assert 'systemctl --user is-active --quiet agentos-action-relay.service' in text
    assert 'systemctl --user is-active --quiet agentos-realm-fabric.service' in text
    assert 'curl -fsS --max-time 5 http://127.0.0.1:8780/v1/health' in text
    assert '"node.runtime.converge" in set(manifest.get("capabilities") or [])' in text


def test_bootstrap_has_no_generic_execution_inputs():
    text = BOOTSTRAP.read_text(encoding="utf-8")
    forbidden = ("$3", "$4", "eval ", "bash -c", "sh -c", "--command", "--argv", "--module", "--executable")
    for token in forbidden:
        assert token not in text


def test_existing_manual_deploy_workflow_requires_explicit_opt_in_and_exact_sha():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "bootstrap_runtime_converger:" in text
    assert "default: false" in text
    assert "expected_sha:" in text
    assert 'Runtime converger bootstrap requires deploy_ref=core/integration' in text
    assert 'Runtime converger bootstrap requires exact lowercase expected_sha' in text
    assert '[ "$TARGET_SHA" = "$EXPECTED" ]' in text
    assert 'bash scripts/bootstrap_runtime_converger_oracle.sh "$REF" "$TARGET_SHA"' in text


def test_failed_bootstrap_revokes_advertisement_before_realm_restore():
    text = WORKFLOW.read_text(encoding="utf-8")
    marker_remove = text.index('rm -f "$CAPABILITY_MARKER"')
    realm_restore = text.index('bash scripts/install_realm_fabric_user.sh || true')
    assert marker_remove < realm_restore
    assert "ONE cannot claim a capability whose rollback state is ambiguous" in text
