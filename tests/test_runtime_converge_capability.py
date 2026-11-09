from __future__ import annotations

import json
from pathlib import Path

from agent_core import realm_server
from agent_core.runtime_converge_capability import (
    ALLOWED_SOURCE_REF,
    MARKER_ACTION,
    MARKER_SCHEMA,
    NODE_CAPABILITY,
    EXPECTED_ACTIONS,
    EXPECTED_NODE_CAPABILITIES,
    default_marker_path,
    installed_core_capabilities,
    validate_installed_marker,
)


SHA = "a" * 40


def marker(**overrides):
    payload = {
        "schema": MARKER_SCHEMA,
        "actions": sorted(EXPECTED_ACTIONS),
        "node_capabilities": sorted(EXPECTED_NODE_CAPABILITIES),
        "source_ref": ALLOWED_SOURCE_REF,
        "source_commit": SHA,
        "observed_at": "2026-09-04T03:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_valid_installed_marker_advertises_exact_installed_core_capabilities(tmp_path: Path):
    path = tmp_path / "capabilities.json"
    path.write_text(json.dumps(marker()), encoding="utf-8")
    assert set(installed_core_capabilities(path)) == EXPECTED_NODE_CAPABILITIES
    validated = validate_installed_marker(marker())
    assert validated is not None
    assert validated["source_commit"] == SHA
    assert set(validated["actions"]) == EXPECTED_ACTIONS


def test_default_marker_follows_runtime_data_root(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AGENT_DATA_ROOT", str(tmp_path))
    path = tmp_path / "runtime" / "action-relay" / "capabilities.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(marker()), encoding="utf-8")
    assert default_marker_path() == path
    assert set(installed_core_capabilities()) == EXPECTED_NODE_CAPABILITIES


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
        marker(actions=sorted(EXPECTED_ACTIONS | {"shell.exec"})),
        marker(node_capabilities=sorted(EXPECTED_NODE_CAPABILITIES | {"shell.exec"})),
    ]
    for payload in cases:
        assert validate_installed_marker(payload) is None


def test_core_manifest_does_not_claim_source_only_capability(monkeypatch):
    monkeypatch.setattr(realm_server, "installed_core_capabilities", lambda: [])
    manifest = realm_server._core_node_manifest("realm-test")
    assert NODE_CAPABILITY not in manifest["capabilities"]


def test_core_manifest_advertises_only_after_installed_marker(monkeypatch):
    monkeypatch.setattr(realm_server, "installed_core_capabilities", lambda: sorted(EXPECTED_NODE_CAPABILITIES))
    manifest = realm_server._core_node_manifest("realm-test")
    for capability in EXPECTED_NODE_CAPABILITIES:
        assert manifest["capabilities"].count(capability) == 1


def test_installer_publishes_marker_only_after_stable_liveness():
    text = (Path(__file__).resolve().parent.parent / "scripts" / "install_action_relay_user.sh").read_text(encoding="utf-8")
    stable_gate = text.index('if [ "$stable" -lt 3 ]')
    marker_write = text.index('capability_marker_payload')
    assert stable_gate < marker_write
    assert 'rm -f "$CAPABILITY_MARKER"' in text
    assert "runtime_converge_action_loaded=PASS" in text
    assert "content_publish_x_auth_action_loaded=PASS" in text
    assert "content_publish_social_actions_loaded=PASS" in text
