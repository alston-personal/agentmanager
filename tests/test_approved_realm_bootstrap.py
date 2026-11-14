"""Approved CREATE -> isolated Realm bootstrap and owner-scoped status tests."""
from __future__ import annotations

import hashlib
import json
from unittest.mock import patch

import pytest

from agent_core.realm_provisioning import (
    ProvisioningError, provision_approved_create, provisioned_request,
    owner_realm, account_virtual_one, reconcile_approved_creates,
)


def fixture_request(tmp_path):
    digest = hashlib.sha256(("google" + "\x00" + "applicant-001").encode()).hexdigest()
    request_id = "realm-onboarding-" + digest[:32]
    root = tmp_path / "requests"
    root.mkdir()
    (root / (digest + ".json")).write_text(json.dumps({
        "schema": "agentos.account-realm-onboarding/v1",
        "request_id": request_id, "actor": digest, "provider": "google",
        "kind": "create", "realm_id": None, "provisioned": False,
    }), encoding="utf-8")
    approval = {
        "id": request_id, "action_type": "realm.onboarding.request",
        "actor": "oauth-account:" + digest[:16],
        "status": "APPROVED",
        "resolved_by": "platform-oauth:" + "a" * 16,
        "payload": {"request_id": request_id, "kind": "create"},
    }
    return root, request_id, digest, approval


def test_approved_create_real_isolation_owner_binding_idempotent(tmp_path):
    root, request_id, digest, approval = fixture_request(tmp_path)
    tenant_root = tmp_path / "realms"
    box = {"history": [approval]}
    result = provision_approved_create(
        request_id, request_root=root, tenants_root=tenant_root, box=box)
    assert result["ok"] is True
    assert result["state"] == "realm_initialized"
    assert result["one_runtime_attested"] is False
    rid = "realm-u-" + digest[:24]
    assert result["realm_id"] == rid
    assert result == provision_approved_create(
        request_id, request_root=root, tenants_root=tenant_root, box=box)
    owner = json.loads((tenant_root / rid / "owner.json").read_text())
    assert owner["owner_digest"] == digest and owner["role"] == "owner"
    assert "applicant-001" not in json.dumps(owner)
    fabric = json.loads((tenant_root / rid / "fabric.json").read_text())
    assert fabric["realm_id"] == rid
    assert provisioned_request(request_id, request_root=root, tenants_root=tenant_root)["bootstrap_verified"]
    valid_identity = {"provider": "google", "subject": "applicant-001", "role": "user"}
    assert owner_realm(valid_identity, tenants_root=tenant_root)["role"] == "owner"
    assert owner_realm({"provider": "google", "subject": "someone-else"}, tenants_root=tenant_root) is None
    assert owner_realm({"provider": "github", "subject": "applicant-001"}, tenants_root=tenant_root) is None


def test_no_approval_no_owner_no_provisioning(tmp_path):
    root, request_id, digest, approval = fixture_request(tmp_path)
    for history in ([], [{**approval, "status": "REJECTED"}],
                    [{**approval, "resolved_by": "platform-oauth:" + digest[:16]}],
                    [{**approval, "actor": "oauth-account:wrong"}]):
        with pytest.raises(ProvisioningError):
            provision_approved_create(
                request_id, request_root=root,
                tenants_root=tmp_path / "managed", box={"history": history},
            )
    assert not (tmp_path / "managed").exists()


def test_tampered_existing_owner_does_not_get_overwritten(tmp_path):
    root, request_id, digest, approval = fixture_request(tmp_path)
    managed = tmp_path / "managed"
    tenant = managed / ("realm-u-" + digest[:24])
    tenant.mkdir(parents=True)
    (tenant / "owner.json").write_text('{"owner_digest":"OTHER"}')
    with pytest.raises(ProvisioningError, match="tenant_owner_conflict"):
        provision_approved_create(
            request_id, request_root=root, tenants_root=managed,
            box={"history": [approval]},
        )
    assert json.loads((tenant / "owner.json").read_text())["owner_digest"] == "OTHER"
    assert not (tenant / "bootstrap-receipt.json").exists()


def test_historical_approved_reconciled_without_extra_decision(tmp_path):
    root, request_id, digest, approval = fixture_request(tmp_path)
    tenants = tmp_path / "tenants"
    box = {"history": [approval]}
    a = reconcile_approved_creates(request_root=root, tenants_root=tenants, box=box)
    b = reconcile_approved_creates(request_root=root, tenants_root=tenants, box=box)
    assert a == b == {"approved_create": 1, "initialized": 1, "blocked": 0}
    assert provisioned_request(request_id, request_root=root, tenants_root=tenants)


def test_virtual_one_api_denies_other_accounts_and_anonymous(tmp_path):
    root, request_id, digest, approval = fixture_request(tmp_path)
    tenants = tmp_path / "tenants"
    provision_approved_create(request_id, request_root=root, tenants_root=tenants,
                              box={"history": [approval]})
    host = "agentos.milkcat.org"
    with patch("agent_core.realm_provisioning._current_identity", return_value=None):
        code, data = account_virtual_one(host=host, cookie=None, tenants_root=tenants)
        assert code == 401 and data["error"] == "signin_required"
    with patch("agent_core.realm_provisioning._current_identity",
               return_value={"provider": "github", "subject": "another", "role": "admin"}):
        code, data = account_virtual_one(host=host, cookie="any", tenants_root=tenants)
        assert code == 403 and data["error"] == "realm_membership_required"
    with patch("agent_core.realm_provisioning._current_identity",
               return_value={"provider": "google", "subject": "applicant-001", "role": "user"}):
        code, data = account_virtual_one(host=host, cookie="valid", tenants_root=tenants)
        assert code == 200 and data["role"] == "owner"
        assert data["one_runtime_attested"] is False
        assert account_virtual_one(host="studio.milkcat.org", cookie="valid",
                                   tenants_root=tenants)[0] == 400


def test_anonymous_my_one_page_follows_api_denial_reason_source_contract():
    import inspect
    from agent_core.distributed_gateway import DistributedGatewayHandler
    source = inspect.getsource(DistributedGatewayHandler.do_GET)
    assert 'result.get("error", "realm_membership_required")' in source
    assert "account_virtual_one" in source


@pytest.mark.parametrize("source_commit", [None, "a" * 40])
def test_bootstrap_transport_repair_does_not_reinstall_legacy_integration(source_commit):
    """The existing control-plane PR suite exercises the canonical repair path."""
    from agentos_node import bootstrap_control
    with patch.object(bootstrap_control, "_run_canonical_script", return_value={"ok": True}) as run:
        receipt = bootstrap_control._execute(bootstrap_control.ACTION_REPAIR_TRANSPORT, source_commit)
    assert receipt == {"ok": True}
    run.assert_called_once_with(
        "scripts/repair_antigravity_relay_user.sh",
        timeout=180,
        source_commit=source_commit,
        env_extra={"AGENTOS_ACTION_SPOOL_PREPROVISIONED": "1", "AGENTOS_REF": "main"},
    )


def test_manual_chronos_workflow_is_never_auto_dispatched():
    root = __import__('pathlib').Path(__file__).resolve().parents[1]
    wf = (root / ".github/workflows/oracle-bootstrap-action-relay-via-chronos-safe.yml").read_text()
    assert "  workflow_dispatch:" in wf
    assert "  contents: read" in wf
    assert "git push origin HEAD:main" not in wf
    assert "persist-credentials: false" in wf
    assert "\n  push:" not in wf
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in wf
    assert 'AGENTOS_SOURCE_COMMIT="$GITHUB_SHA" bash scripts/bootstrap_action_relay_via_chronos_safe_v2.sh' in wf


def test_chronos_bridge_pins_script_and_installer_to_exact_main_sha():
    root = __import__('pathlib').Path(__file__).resolve().parents[1]
    script = (root / "scripts/bootstrap_action_relay_via_chronos_safe_v2.sh").read_text()
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
    root = __import__('pathlib').Path(__file__).resolve().parents[1]
    script_path = root / "scripts/bootstrap_action_relay_via_chronos_safe_v2.sh"
    result = subprocess.run(["bash", "-n", str(script_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    text = script_path.read_text()
    marker = """python3 - "$TARGET" "$REQUEST_ID" "$RECEIPT" "$PINNED_SOURCE_COMMIT" <<'PY'""" + chr(10)
    assert marker in text
    generator = text.split(marker, 1)[1].split(chr(10) + "PY" + chr(10), 1)[0]
    compile(generator, str(script_path) + ":bridge-generator", "exec")

