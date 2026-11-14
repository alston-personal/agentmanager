"""The existing emergency Chronos bridge must pin a protected-main exact source."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manual_chronos_workflow_is_never_auto_dispatched():
    wf = (ROOT / ".github/workflows/oracle-bootstrap-action-relay-via-chronos-safe.yml").read_text()
    assert "  workflow_dispatch:" in wf
    assert "  contents: read" in wf
    assert "git push origin HEAD:main" not in wf
    assert "persist-credentials: false" in wf
    assert "\n  push:" not in wf
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in wf
    assert 'AGENTOS_SOURCE_COMMIT="$GITHUB_SHA" bash scripts/bootstrap_action_relay_via_chronos_safe_v2.sh' in wf


def test_chronos_bridge_pins_script_and_installer_to_exact_main_sha():
    script = (ROOT / "scripts/bootstrap_action_relay_via_chronos_safe_v2.sh").read_text()
    assert 'PINNED_SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"' in script
    assert "safe_chronos_pinned_main_commit_required" in script
    assert "git merge-base --is-ancestor {expected_commit} origin/main" in script
    assert "git show {expected_commit}:scripts/repair_antigravity_relay_user.sh" in script
    assert "AGENTOS_REF=main AGENTOS_SOURCE_COMMIT={expected_commit}" in script
    assert "git show origin/main:scripts/repair_antigravity_relay_user.sh" not in script
    assert "assert 'action_relay_source_commit='+sys.argv[2] in text" in script
    assert "trap restore_target EXIT" in script
    assert "restore_target" in script

def test_safe_chronos_script_parses_and_compiles_bridge_generator():
    import subprocess
    script_path = ROOT / "scripts/bootstrap_action_relay_via_chronos_safe_v2.sh"
    result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    text = script_path.read_text()
    marker = """python3 - "$TARGET" "$REQUEST_ID" "$RECEIPT" "$PINNED_SOURCE_COMMIT" <<'PY'""" + chr(10)
    assert marker in text
    generator = text.split(marker, 1)[1].split(chr(10) + "PY" + chr(10), 1)[0]
    compile(generator, str(script_path) + ":bridge-generator", "exec")
