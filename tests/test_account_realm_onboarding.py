from unittest.mock import patch

from agent_core.account_realm_onboarding import account_request
from agent_core.companion_web import render_welcome_html


HOST = "agentos.milkcat.org"
ORIGIN = "https://agentos.milkcat.org"


def test_anonymous_cannot_request_or_read_realm(tmp_path):
    with patch("agent_core.account_realm_onboarding._current_identity", return_value=None):
        for method in ("GET", "POST"):
            status, result = account_request(
                method=method, host=HOST, cookie=None, origin=ORIGIN,
                body={"kind": "create"}, root=tmp_path,
            )
            assert status == 401 and result["error"] == "signin_required"
    assert list(tmp_path.iterdir()) == []


def test_same_origin_create_request_is_pending_never_provisioned(tmp_path):
    actor = {"provider": "google", "subject": "test-user-001", "role": "user"}
    with patch("agent_core.account_realm_onboarding._current_identity", return_value=actor), patch(
        "agent_core.account_realm_onboarding.park_approval"
    ) as park:
        status, initial = account_request(
            method="GET", host=HOST, cookie="agentos_auth_token=test", origin=None, root=tmp_path,
        )
        assert status == 200 and initial["state"] == "not_requested"
        assert initial["role"] == "user"
        status, result = account_request(
            method="POST", host=HOST, cookie="agentos_auth_token=test", origin=ORIGIN,
            body={"kind": "create"}, root=tmp_path,
        )
        assert status == 202 and result["state"] == "pending_review"
        assert result["realm_id"] is None
        park.assert_called_once()
        kwargs = park.call_args.kwargs
        assert kwargs["action_type"] == "realm.onboarding.request"
        assert kwargs["payload"]["provisioned"] is False
        assert actor["subject"] not in str(kwargs)
        assert "realm-alston" not in str(kwargs)
        assert actor["subject"] not in list(tmp_path.iterdir())[0].read_text()

        status2, result2 = account_request(
            method="POST", host=HOST, cookie="same", origin=ORIGIN,
            body={"kind": "create"}, root=tmp_path,
        )
        assert status2 == 200 and result2["request_id"] == result["request_id"]
        park.assert_called_once()


def test_join_request_requires_valid_realm_and_origin(tmp_path):
    actor = {"provider": "github", "subject": "test-user-002", "role": "user"}
    with patch("agent_core.account_realm_onboarding._current_identity", return_value=actor), patch(
        "agent_core.account_realm_onboarding.park_approval"
    ) as park:
        for origin in (None, "https://studio.milkcat.org"):
            code, body = account_request(
                method="POST", host=HOST, cookie="x", origin=origin,
                body={"kind": "join", "realm_id": "realm-sample"}, root=tmp_path,
            )
            assert code == 403 and body["error"] == "invalid_origin"
        for value in ("", "../realm-alston", "REALM/OTHER"):
            code, body = account_request(
                method="POST", host=HOST, cookie="x", origin=ORIGIN,
                body={"kind": "join", "realm_id": value}, root=tmp_path,
            )
            assert code == 400
        code, result = account_request(
            method="POST", host=HOST, cookie="x", origin=ORIGIN,
            body={"kind": "join", "realm_id": "realm-example"}, root=tmp_path,
        )
        assert code == 202 and result["realm_id"] == "realm-example"
        assert result["state"] == "pending_review"
        assert park.call_count == 1


def test_welcome_has_real_action_controls_with_no_root_elevation():
    html = render_welcome_html()
    assert 'id="create-realm"' in html
    assert 'id="join-realm-submit"' in html
    assert "/v1/account/realm-request" in html
    assert "管理者 Console 不會自動開放" in html
    assert "realm-alston" not in html


def test_applicant_sees_real_review_state_not_false_realm_activation(tmp_path):
    actor = {"provider": "google", "subject": "test-applicant-001", "role": "user"}
    with patch("agent_core.account_realm_onboarding._current_identity", return_value=actor), patch(
        "agent_core.account_realm_onboarding.park_approval"
    ), patch("agent_core.account_realm_onboarding.load_box", return_value={"history": []}) as box:
        code, created = account_request(
            method="POST", host=HOST, cookie="x", origin=ORIGIN,
            body={"kind": "create"}, root=tmp_path,
        )
        assert code == 202 and created["kind"] == "create"
        request_id = created["request_id"]
        box.return_value = {"history": [{"id": request_id,
                             "action_type": "realm.onboarding.request", "status": "APPROVED"}]}
        code, state = account_request(method="GET", host=HOST, cookie="x", origin=None, root=tmp_path)
        assert code == 200 and state["state"] == "approved_pending_provisioning"
        assert state["kind"] == "create" and state["provisioned"] is False
        box.return_value = {"history": [{"id": request_id,
                             "action_type": "realm.onboarding.request", "status": "REJECTED"}]}
        code, state = account_request(method="GET", host=HOST, cookie="x", origin=None, root=tmp_path)
        assert code == 200 and state["state"] == "rejected"
        assert state["provisioned"] is False
