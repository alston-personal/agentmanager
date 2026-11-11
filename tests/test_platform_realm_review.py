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
    assert "核准（待 ONE 開通）" in html
    assert "operator token" not in html.lower()
