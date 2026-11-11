from hashlib import sha256
from unittest.mock import patch

from agent_core.platform_realm_review import platform_review
from agent_core.companion_web import render_platform_review_html


HOST = "agentos.milkcat.org"
ORIGIN = "https://agentos.milkcat.org"
ID = "realm-onboarding-" + "a" * 32
REQUEST = {
    "id": ID, "action_type": "realm.onboarding.request",
    "actor": "oauth-account:example", "status": "AWAITING_HUMAN_APPROVAL",
    "payload": {"request_id": ID, "kind": "create", "realm_id": None},
}


def test_unauthorized_and_non_admin_denied_even_direct_api():
    with patch("agent_core.platform_realm_review._current_identity", return_value=None):
        code, data = platform_review(method="GET", host=HOST, cookie=None, origin=None)
        assert code == 401 and data["error"] == "signin_required"
    with patch("agent_core.platform_realm_review._current_identity",
               return_value={"provider": "google", "subject": "ordinary", "role": "user"}):
        code, data = platform_review(method="GET", host=HOST, cookie="session", origin=None)
        assert code == 403 and data["error"] == "platform_admin_required"
        code, data = platform_review(method="POST", host=HOST, cookie="session",
                                     origin=ORIGIN, body={"request_id": ID, "decision": "approve"})
        assert code == 403
    with patch("agent_core.platform_realm_review._current_identity",
               return_value={"provider": "google", "subject": "admin", "role": "admin"}):
        assert platform_review(method="POST", host=HOST, cookie="x", origin="https://studio.milkcat.org",
                               body={"request_id": ID, "decision": "approve"})[0] == 403
        assert platform_review(method="GET", host="studio.milkcat.org", cookie="x", origin=None)[0] == 400


def test_admin_can_review_only_realm_requests_not_general_approvals():
    admin = {"provider": "google", "subject": "admin-subject", "role": "admin"}
    other = {"id": "secret-approval", "action_type": "delete_project", "status": "AWAITING_HUMAN_APPROVAL"}
    box = {"pending_approvals": [REQUEST, other], "history": []}
    with patch("agent_core.platform_realm_review._current_identity", return_value=admin), patch(
        "agent_core.platform_realm_review.load_box", return_value=box
    ), patch("agent_core.platform_realm_review.resolve_approval") as resolve:
        code, results = platform_review(method="GET", host=HOST, cookie="x", origin=None)
        assert code == 200 and len(results["pending"]) == 1
        assert results["pending"][0]["kind"] == "create"
        assert "actor" not in results["pending"][0]
        code, result = platform_review(
            method="POST", host=HOST, cookie="x", origin=ORIGIN,
            body={"request_id": "secret-approval", "decision": "approve"}
        )
        assert code == 400
        code, result = platform_review(
            method="POST", host=HOST, cookie="x", origin=ORIGIN,
            body={"request_id": ID, "decision": "approve"}
        )
        resolve.assert_called_once()
        assert code == 409 or code == 200
        assert result.get("membership_granted") is not True


def test_self_review_forbidden():
    subject = "same-account"
    digest = sha256(("google" + "\x00" + subject).encode()).hexdigest()
    request = {**REQUEST, "actor": "oauth-account:" + digest[:16]}
    admin = {"provider": "google", "subject": subject, "role": "admin"}
    with patch("agent_core.platform_realm_review._current_identity", return_value=admin), patch(
        "agent_core.platform_realm_review.load_box",
        return_value={"pending_approvals": [request], "history": []}
    ), patch("agent_core.platform_realm_review.resolve_approval") as resolve:
        code, result = platform_review(method="POST", host=HOST, cookie="x",
                                       origin=ORIGIN, body={"request_id": ID, "decision": "approve"})
        assert code == 403 and result["error"] == "self_review_forbidden"
        resolve.assert_not_called()


def test_platform_ui_has_review_operations_but_no_provisioning_claim():
    html = render_platform_review_html()
    assert "平台治理" in html
    assert "/v1/platform/realm-requests" in html
    assert "核准申請（不代表開通）" in html
    assert "operator token" not in html.lower()


def test_review_denial_reasons_are_distinct():
    from agent_core.platform_realm_review import platform_review
    with patch("agent_core.platform_realm_review._current_identity", return_value=None):
        status, body = platform_review(method="GET", host=HOST, cookie=None, origin=None)
        assert status == 401 and body["error"] == "signin_required"
    with patch("agent_core.platform_realm_review._current_identity",
               return_value={"provider": "google", "subject": "not-authorized", "role": "user"}):
        status, body = platform_review(method="GET", host=HOST, cookie="test", origin=None)
        assert status == 403 and body["error"] == "platform_admin_required"


def test_platform_access_denial_pages_offer_login_or_account_switch():
    from agent_core.companion_web import render_platform_auth_gate_html
    login = render_platform_auth_gate_html(authenticated=False)
    assert "需要使用已獲授權的平台管理者帳號登入" in login
    for provider in ("google", "github", "facebook", "line"):
        assert "/dashboard/api/auth/signin/" + provider in login
    assert login.count("returnTo=%2Fplatform") == 4
    assert "/welcome" in login
    assert "核准（待 ONE 開通）" not in login

    forbidden = render_platform_auth_gate_html(authenticated=True)
    assert "目前帳號沒有平台管理權限" in forbidden
    assert "/dashboard/api/auth/logout?returnTo=%2Fplatform" in forbidden
    assert "/welcome" in forbidden
    assert "核准（待 ONE 開通）" not in forbidden


def test_reviewer_sees_only_verified_applicant_identity(tmp_path):
    from agent_core.platform_realm_review import _applicant, _project
    digest = "a" * 64
    request_id = "realm-onboarding-" + digest[:32]
    (tmp_path / (digest + ".json")).write_text(
        __import__("json").dumps({"request_id": request_id, "actor": digest,
                                  "provider": "google",
                                  "applicant_display_name": "Sample Applicant",
                                  "subject": "sensitive-provider-subject"}),
        encoding="utf-8",
    )
    applicant = _applicant(request_id, "oauth-account:" + digest[:16], root=tmp_path)
    assert applicant["name"] == "Sample Applicant"
    assert applicant["provider"] == "google"
    assert "subject" not in applicant
    assert _applicant(request_id, "oauth-account:not-valid", root=tmp_path)["provider"] == "unknown"


def test_platform_review_ui_has_broader_governance_navigation_and_details():
    html = render_platform_review_html()
    assert "平台治理中心" in html
    assert "Realm 清冊（尚未開放）" in html
    assert "節點與資源（尚未開放）" in html
    assert "近期審核紀錄" in html
    for key in ("申請人", "登入來源", "申請時間", "審核狀態", "Realm 初始化", "ONE 執行服務"):
        assert key in html
    assert "innerHTML" not in html


def test_welcome_always_links_back_to_protected_platform():
    from agent_core.companion_web import render_welcome_html
    html = render_welcome_html()
    assert 'href="/platform"' in html
    assert 'href="/welcome" aria-current="page"' in html
    assert "平台治理（需管理權限）" in html
    assert "登入首頁" in html


def test_approved_platform_item_shows_true_next_step_without_fake_one():
    html = render_platform_review_html()
    assert "等待獨立 ONE 建立與帳號 Owner 綁定" in html
    assert "已核准申請會移至下方近期審核紀錄" in html
    assert "Realm 初始化" in html
    assert "ONE 執行服務" in html
