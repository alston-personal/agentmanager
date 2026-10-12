from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lobster_systemd_unit_has_bounded_stop_contract() -> None:
    text = (ROOT / "scripts" / "install_systemd_user.sh").read_text(encoding="utf-8")
    start = text.index('cat > "$USER_SYSTEMD_DIR/os-lobster.service" <<EOF')
    end = text.index("\nEOF\n", start)
    block = text[start:end]

    assert "TimeoutStopSec=15s" in block
    assert "KillMode=control-group" in block
    assert "SendSIGKILL=yes" in block


def test_immutable_convergence_emits_lobster_restart_boundaries() -> None:
    text = (
        ROOT
        / ".github"
        / "workflows"
        / "oracle-core-bundle-immutable-runtime-convergence.yml"
    ).read_text(encoding="utf-8")

    assert 'core_bundle_install_services=START' in text
    assert 'core_bundle_install_services=DONE' in text
    assert 'core_bundle_lobster_restart=START' in text
    assert 'core_bundle_lobster_restart=DONE' in text
