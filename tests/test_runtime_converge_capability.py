from __future__ import annotations

import json
from pathlib import Path

from agent_core import realm_server
from agent_core.runtime_converge_capability import (
    ALLOWED_SOURCE_REF,
    MARKER_ACTION,
    MARKER_SCHEMA,
    NODE_CAPABILITY,
    default_marker_path,
    installed_core_capabilities,
    validate_installed_marker,
)


SHA = "a" * 40


def marker(**overrides):
    payload = {
        "schema": MARKER_SCHEMA,
        "actions": ["agentos.executor.job", MARKER_ACTION],
        "node_capabilities": [NODE_CAPABILITY],
        "source_ref": ALLOWED_SOURCE_REF,
        "source_commit": SHA,
        "observed_at": "2026-09-04T03:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_valid_installed_marker_advertises_only_runtime_converge(tmp_path: Path):
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(marker()), encoding="utf-8")
    assert installed_core_capabilities(path) == [NODE_CAPABILITY]
    validated = validate_installed_marker(marker())
    assert validated is not None
    assert validated["source_commit"] == SHA


def test_default_marker_follows_runtime_data_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_DATA_ROOT", str(tmp_path))
    path = tmp_path / "runtime" / "action-relay" / "capabilities.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(marker()), encoding="utf-8")
    assert default_marker_path() == path
    assert installed_core_capabilities() == [NODE_CAPABILITY]


def test_missing_corrupt_or_wrong_provenance_marker_fails_closed(tmp_path: Path):
    missing = tmp_path / "missing.json"
    assert installed_core_capabilities(missing) == []

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("not-json", encoding="utf-8")
    assert installed_core_capabilities(corrupt) == []

    cases = [
        marker(schema="wrong"),
        marker(source_ref="main"),
        marker(source_commit="abc"),
        marker(actions=["agentos.executor.job"]),
        marker(actions=["agentos.executor.job", MARKER_ACTION, "shell.exec"]),
        marker(node_capabilities=[NODE_CAPABILITY, "shell.exec"]),
    ]
    for payload in cases:
        assert validate_installed_marker(payload) is None


def test_core_manifest_does_not_claim_source_only_capability(monkeypatch):
    monkeypatch.setattr(realm_server, "installed_core_capabilities", lambda: [])
    manifest = realm_server._core_node_manifest("realm-test")
    assert NODE_CAPABILITY not in manifest["capabilities"]


def test_core_manifest_advertises_only_after_installed_marker(monkeypatch):
    monkeypatch.setattr(realm_server, "installed_core_capabilities", lambda: [NODE_CAPABILITY])
    manifest = realm_server._core_node_manifest("realm-test")
    assert manifest["capabilities"].count(NODE_CAPABILITY) == 1


def test_installer_publishes_marker_only_after_stable_liveness():
    text = (Path(__file__).resolve().parent.parent / "scripts" / "install_action_relay_user.sh").read_text(encoding="utf-8")
    stable_gate = text.index('if [ "$stable" -lt 3 ]')
    marker_write = text.index('capability_marker_payload')
    assert stable_gate < marker_write
    assert 'rm -f "$CAPABILITY_MARKER"' in text
    assert "runtime_converge_action_loaded=PASS" in text


def test_marker_publication_uses_fixed_group_and_preserves_old_temp(tmp_path):
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    source = (repo / 'scripts/install_action_relay_user.sh').read_text()
    command = source.split('AGENTOS_MARKER_PATH=', 1)[1].split('\necho "action_relay_install=PASS"', 1)[0]
    command = 'AGENTOS_MARKER_PATH=' + command
    # Exercise the installer publication block without installing/restarting services.
    # The shim verifies sg routing and runs its fixed command; OS group enrollment
    # remains a live acceptance requirement.
    shim = tmp_path / 'sg'
    shim.write_text('#!' + sys.executable + '\n'
                    'import subprocess,sys\n'
                    'assert sys.argv[1:3] == ["agentos", "-c"]\n'
                    'assert sys.argv[3].startswith("exec python3 - ")\n'
                    'raise SystemExit(subprocess.call(["/bin/sh", "-c", sys.argv[3]]))\n')
    shim.chmod(0o755)
    shared = tmp_path / "shared ' $(false)"
    shared.mkdir()
    old_temp = shared / 'capabilities.tmp'
    old_temp.write_text('preserve prior evidence')
    env = dict(os.environ, PATH=str(tmp_path) + ':' + os.environ['PATH'],
               CAPABILITY_MARKER=str(shared / 'capabilities.json'),
               RUNTIME_ROOT=str(repo), SOURCE_REF='core/integration', SOURCE_COMMIT='a' * 40)
    subprocess.run(['bash', '-e', '-c', command], env=env, check=True, capture_output=True)
    assert validate_installed_marker(__import__('json').loads((shared / 'capabilities.json').read_text())) is not None
    assert old_temp.read_text() == 'preserve prior evidence'
    assert not list(shared.glob('.capabilities-*.tmp'))
    # A group-entry failure must propagate and leave the accepted marker intact.
    before = (shared / 'capabilities.json').read_bytes()
    shim.write_text('#!/bin/sh\nexit 17\n')
    result = subprocess.run(['bash', '-e', '-c', command], env=env, capture_output=True)
    assert result.returncode == 17
    assert (shared / 'capabilities.json').read_bytes() == before
