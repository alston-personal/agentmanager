from unittest.mock import patch
from agent_core.virtual_one_nodes import owner_node_map, owner_approve_code, device_join
from agent_core.realm_provisioning import provision_approved_create

HOST="agentos.milkcat.org"
ORIGIN="https://agentos.milkcat.org"


def boot(tmp_path):
    from test_approved_realm_bootstrap import fixture_request
    root, request_id, digest, approval = fixture_request(tmp_path)
    tenants=tmp_path/"managed"
    result=provision_approved_create(request_id, request_root=root,
                                     tenants_root=tenants, box={"history":[approval]})
    realm_id=result["realm_id"]
    return tenants, realm_id


def test_owner_node_map_and_code_approval_complete_device_claim(tmp_path):
    tenants, realm_id=boot(tmp_path)
    me={"provider":"google","subject":"applicant-001","role":"user"}
    someone_else={"provider":"google","subject":"stranger","role":"admin"}
    manifest={"schema":"agentos.node-manifest/v0.1",
              "realm_id":realm_id,"node_id":"node-one","role":"client",
              "capabilities":["capture"]}
    status, initiated=device_join(host=HOST,realm_id=realm_id,action="request",
                                  body={"manifest":manifest},root=tenants)
    assert status==200
    assert initiated["realm_id"]==realm_id
    assert initiated["user_code"]
    assert initiated["claim_secret"]
    with patch("agent_core.virtual_one_nodes._current_identity",return_value=None):
        assert owner_node_map(host=HOST,cookie=None,root=tenants)[0]==401
    with patch("agent_core.virtual_one_nodes._current_identity",return_value=someone_else):
        assert owner_node_map(host=HOST,cookie="x",root=tenants)[0]==403
        assert owner_approve_code(host=HOST,cookie="x",origin=ORIGIN,
                                  code=initiated["user_code"],root=tenants)[0]==403
    with patch("agent_core.virtual_one_nodes._current_identity",return_value=me):
        code, info=owner_node_map(host=HOST,cookie="x",root=tenants)
        assert code==200 and info["node_count"]==0
        assert len(info["pending_joins"])==1
        assert "claim_secret" not in str(info)
        assert owner_approve_code(host=HOST,cookie="x",
                 origin="https://studio.milkcat.org",
                 code=initiated["user_code"],root=tenants)[0]==403
        code, approved=owner_approve_code(host=HOST,cookie="x",
                              origin=ORIGIN,code=initiated["user_code"],root=tenants)
        assert code==200 and approved["status"]=="approved_pending_node_claim"
        assert approved["node_id"]=="node-one"
    # Prove a code alone cannot be used to claim credentials.
    assert device_join(host=HOST,realm_id=realm_id,action="claim",body={
        "request_id":initiated["request_id"],"claim_secret":"wrong"
    },root=tenants)[0]==403
    code, claimed=device_join(host=HOST,realm_id=realm_id,action="claim",body={
        "request_id":initiated["request_id"],"claim_secret":initiated["claim_secret"]
    },root=tenants)
    assert code==200 and claimed["ok"] is True
    assert claimed["realm_id"]==realm_id
    with patch("agent_core.virtual_one_nodes._current_identity",return_value=me):
        code, nodes=owner_node_map(host=HOST,cookie="x",root=tenants)
        assert code==200 and nodes["node_count"]==1
        assert nodes["nodes"][0]["node_id"]=="node-one"
        assert nodes["pending_joins"]==[]


def test_realm_selector_never_grants_access_to_other_owner(tmp_path):
    tenants, realm_id=boot(tmp_path)
    assert device_join(host="studio.milkcat.org",realm_id=realm_id,
                       action="request",body={},root=tenants)[0]==400
    assert device_join(host=HOST,realm_id="realm-alston",
                       action="request",body={},root=tenants)[0]==400
    assert device_join(host=HOST,realm_id=realm_id,
                       action="request",body={"manifest":{"realm_id":"realm-alston"}},
                       root=tenants)[0]==403
    with patch("agent_core.virtual_one_nodes._current_identity",
               return_value={"provider":"google","subject":"applicant-001"}):
        assert owner_approve_code(host=HOST,cookie="x",origin=ORIGIN,
                                  code="XXXX-XXXX",root=tenants)[0]==409
        assert owner_approve_code(host=HOST,cookie="x",origin=ORIGIN,
                                  code="ABCD-EFGH",root=tenants)[0]==409


def test_virtual_one_html_supports_code_approval_and_map():
    from agent_core.companion_web import render_my_one_html
    html=render_my_one_html()
    assert 'id="agentos-account-identity"' in html
    assert 'session.username' in html
    assert "Node Map" in html
    assert "核准加入 Node" in html
    assert "/v1/account/virtual-one/nodes" in html
    assert "/v1/account/virtual-one/join/approve" in html
    assert "innerHTML" not in html
    assert 'aria-label="AgentOS 帳號與導覽"' in html
    assert 'href="/dashboard/api/auth/logout?returnTo=%2F"' in html
    assert "切換使用者" in html
    assert "登出" in html
    # Both actions must use the site-scoped sign-out endpoint, not client-side Realm switching.
    assert html.count('href="/dashboard/api/auth/logout?returnTo=%2F"') >= 2


def test_tenant_windows_client_request_targets_exact_realm(monkeypatch):
    """Existing ThinClient Join must use the same Realm API as /my-one."""
    import pytest
    from agentos_node.thin_client_transport import ThinClientTransport, device_join_base
    from agentos_node.thin_client import ThinClientPolicy
    realm = 'realm-u-' + 'a' * 24
    seen = []

    def request(url, **kwargs):
        seen.append((url, kwargs))
        return {'ok': True, 'request_id': 'join_' + 'b' * 20,
                'claim_secret': 'secret', 'user_code': 'ABCD-EFGH'}
    monkeypatch.setattr(ThinClientTransport, '_request', staticmethod(request))
    result = ThinClientTransport.request_enrollment(
        one_url='https://agentos.milkcat.org', realm_id=realm,
        node_id='new-client', policy=ThinClientPolicy())
    assert result['ok']
    assert seen[0][0] == 'https://agentos.milkcat.org/v1/realms/' + realm + '/join/request'
    assert seen[0][1]['body']['manifest']['realm_id'] == realm
    assert device_join_base('https://studio.milkcat.org/dashboard/api/agentos') == (
        'https://studio.milkcat.org/dashboard/api/agentos/v1/join')
    with pytest.raises(ValueError, match='invalid_tenant_realm_id'):
        device_join_base('https://agentos.milkcat.org', 'realm-alston')
    with pytest.raises(ValueError, match='tenant_join_requires_agentos_origin'):
        device_join_base('https://studio.milkcat.org', realm)


def test_tenant_device_approval_and_claim_use_scoped_routes(monkeypatch, tmp_path):
    from agentos_node.thin_client_transport import ThinClientTransport
    realm = 'realm-u-' + 'c' * 24
    seen = []

    def request(url, **kwargs):
        seen.append(url)
        if url.endswith('/status'):
            return {'status': 'approved'}
        return {'status': 'enrolled', 'realm_id': realm,
                'node_id': 'one-client', 'node_token': 'test-only'}
    monkeypatch.setattr(ThinClientTransport, '_request', staticmethod(request))
    config = ThinClientTransport.wait_for_approval(
        one_url='https://agentos.milkcat.org', realm_id=realm,
        request_id='join_' + 'a' * 20, claim_secret='test-secret',
        config_path=tmp_path / 'client.json', timeout_seconds=10)
    assert config.realm_id == realm
    assert seen == [
        'https://agentos.milkcat.org/v1/realms/' + realm + '/join/status',
        'https://agentos.milkcat.org/v1/realms/' + realm + '/join/claim',
    ]


def test_tenant_node_scoped_heartbeat_and_owner_map_without_fake_one_runtime(tmp_path):
    from agent_core.virtual_one_nodes import tenant_node_runtime
    tenants, realm_id = boot(tmp_path)
    identity = {"provider": "google", "subject": "applicant-001", "role": "user"}
    manifest = {
        "schema": "agentos.node-manifest/v0.1", "realm_id": realm_id,
        "node_id": "fresh-device", "role": "client",
        "capabilities": ["capture"], "platform": "Windows",
    }
    status, request = device_join(
        host=HOST, realm_id=realm_id, action="request",
        body={"manifest": manifest}, root=tenants)
    assert status == 200
    with patch("agent_core.virtual_one_nodes._current_identity", return_value=identity):
        approved, _ = owner_approve_code(
            host=HOST, cookie="owner-cookie", origin=ORIGIN,
            code=request["user_code"], root=tenants)
        assert approved == 200
    status, claim = device_join(
        host=HOST, realm_id=realm_id, action="claim",
        body={"request_id": request["request_id"], "claim_secret": request["claim_secret"]},
        root=tenants)
    assert status == 200
    token = claim["node_token"]
    heartbeat = {
        "schema": "agentos.node-heartbeat/v0.1",
        "realm_id": realm_id, "node_id": "fresh-device", "status": "online",
        "observed_at": None, "uptime_seconds": 1, "surface_count": 0,
        "manifest": manifest,
    }
    def runtime(action, method="GET", node="fresh-device", secret=token, body=None, host=HOST, realm=realm_id):
        return tenant_node_runtime(host=host, realm_id=realm, action=action,
            method=method, node_id=node, token=secret, body=body, root=tenants)

    assert runtime("health", secret="incorrect")[0] == 403
    assert runtime("health", secret="")[0] == 401
    assert runtime("health", realm="realm-u-" + "f" * 24)[0] != 200
    assert runtime("health")[1]["one_runtime_attested"] is False
    assert runtime("heartbeat", method="POST", body={**heartbeat, "realm_id":"realm-other"})[0] == 403
    assert runtime("heartbeat", method="POST", body=heartbeat)[1]["heartbeat_recorded"] is True
    with patch("agent_core.virtual_one_nodes._current_identity", return_value=identity):
        code, projection = owner_node_map(host=HOST, cookie="owner", root=tenants)
    assert code == 200
    assert projection["online_node_count"] == 1
    assert projection["one_runtime_attested"] is False
    assert runtime("bootstrap")[1]["schema"] == "agentos.node-bootstrap/v0.1"
    assert runtime("tasks")[1]["tasks"] == []
    assert runtime("benchmark", method="POST", body={
        "realm_id": realm_id, "node_id": "fresh-device"})[1]["ok"] is False
    assert runtime("receipts", method="POST", body={
        "schema": "agentos.node-receipt/v0.1", "node_id": "fresh-device",
        "task_id": "unissued"})[0] == 409


def test_tenant_transport_node_endpoints_bind_host_and_realm():
    from agentos_node.thin_client_transport import ClientConfig, node_runtime_endpoint
    cfg = ClientConfig(
        one_url=ORIGIN, realm_id="realm-u-" + "b" * 24,
        node_id="device", node_token="test-only")
    assert node_runtime_endpoint(cfg, "heartbeat") == (
        ORIGIN + "/v1/realms/" + cfg.realm_id + "/heartbeat")
    assert node_runtime_endpoint(cfg, "tasks").endswith("/v1/realms/" + cfg.realm_id + "/tasks")
    legacy = ClientConfig(one_url="https://studio.milkcat.org/dashboard/api/agentos",
                          realm_id="realm-alston", node_id="device", node_token="legacy")
    assert node_runtime_endpoint(legacy, "heartbeat") == (
        "https://studio.milkcat.org/dashboard/api/agentos/v1/heartbeat")


def test_join_stage_only_keeps_active_config_and_never_starts_supervisor(monkeypatch, tmp_path):
    import json
    from agentos_node import client_cli
    from agentos_node.thin_client import ThinClientPolicy
    from agentos_node.thin_client_transport import ClientConfig, ThinClientTransport

    active = tmp_path / "client.json"
    previous = {"realm_id": "realm-alston", "node_id": "same-node", "node_token": "old",
                "one_url": "https://studio.milkcat.org/dashboard/api/agentos"}
    active.write_text(json.dumps(previous), encoding="utf-8")
    stage = tmp_path / "client.stage.json"
    tenant = "realm-u-" + "a" * 24
    monkeypatch.setattr(client_cli, "_load_policy", lambda path: ThinClientPolicy())
    monkeypatch.setattr(client_cli, "install_node_supervisor",
                        lambda: (_ for _ in ()).throw(AssertionError("supervisor must not start")))
    def fake_enroll_device(**kwargs):
        cfg = ClientConfig(one_url=kwargs["one_url"], realm_id=tenant,
                           node_id="same-node", node_token="staged-secret")
        cfg.save(kwargs["config_path"])
        return cfg
    class FakeTransport:
        def health(self): return {"ok": True}
        def heartbeat(self): return {"ok": True, "heartbeat_recorded": True}
    monkeypatch.setattr(ThinClientTransport, "enroll_device", fake_enroll_device)
    monkeypatch.setattr(client_cli, "build_client", lambda cfg, policy: FakeTransport())

    assert client_cli.main(["--config", str(stage), "join", "--one", ORIGIN,
                            "--realm-id", tenant, "--node-id", "same-node",
                            "--stage-only"]) == 0
    assert json.loads(active.read_text(encoding="utf-8")) == previous
    assert json.loads(stage.read_text(encoding="utf-8"))["realm_id"] == tenant
    assert client_cli.main(["--config", str(active), "join", "--one", ORIGIN,
                            "--realm-id", tenant, "--node-id", "same-node",
                            "--stage-only"]) == 2
    assert client_cli.main(["--config", str(stage), "join", "--one", ORIGIN,
                            "--realm-id", tenant, "--node-id", "same-node",
                            "--stage-only"]) == 2
    assert json.loads(active.read_text(encoding="utf-8")) == previous


def test_windows_switch_is_prepare_only_and_cannot_delete_active_config():
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] /
              "scripts/bootstrap_clean_windows_node.ps1").read_text(encoding="utf-8")
    assert "agentos_realm_switch=STAGED_VERIFIED" in script
    assert "agentos_active_binding=PRESERVED" in script
    assert "agentos_realm_switch_cutover=NOT_AUTHORIZED_UNTIL_SUPERVISOR_ROLLBACK_VERIFIED" in script
    assert "client.stage.json" in script
    assert '"--stage-only"' in script
    assert "Remove-Item -LiteralPath $config" not in script
    assert "Copy-Item -LiteralPath $originalPolicy -Destination $policy" in script
