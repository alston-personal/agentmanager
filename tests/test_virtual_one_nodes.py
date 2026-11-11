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
    assert "Node Map" in html
    assert "核准加入 Node" in html
    assert "/v1/account/virtual-one/nodes" in html
    assert "/v1/account/virtual-one/join/approve" in html
    assert "innerHTML" not in html
