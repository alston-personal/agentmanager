"""OAuth-admin-only platform Realm request review.

A platform review records a decision in the existing approval broker; it
NEVER provisions a Realm, grants a membership, or opens an operator Console.
Only explicit platform admin identities in Dashboard's trusted allowlist may
see or decide requests. Ordinary OAuth login has no access.
"""
from __future__ import annotations
import hashlib
from typing import Any

from .account_realm_onboarding import _current_identity
from .approval_broker import load_box, resolve_approval

_HOST = "agentos.milkcat.org"
_ORIGIN = "https://agentos.milkcat.org"
_PREFIX = "realm-onboarding-"


def _project(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("action_type") != "realm.onboarding.request":
        return None
    request_id = str(item.get("id") or "")
    payload = item.get("payload")
    if not request_id.startswith(_PREFIX) or not isinstance(payload, dict):
        return None
    if payload.get("request_id") != request_id:
        return None
    return {
        "request_id": request_id,
        "kind": payload.get("kind"),
        "realm_id": payload.get("realm_id"),
        "status": item.get("status"),
        "parked_at": item.get("parked_at"),
        "resolved_at": item.get("resolved_at"),
        "resolved_by": item.get("resolved_by"),
        # Never project internal account identity or arbitrary payloads.
    }


def platform_review(*, method: str, host: str, cookie: str | None,
                    origin: str | None, body: dict[str, Any] | None = None
                    ) -> tuple[int, dict[str, Any]]:
    if host.lower().split(":")[0] != _HOST:
        return 400, {"ok": False, "error": "invalid_site"}
    if method not in ("GET", "POST"):
        return 405, {"ok": False, "error": "method_not_allowed"}
    if method == "POST" and origin != _ORIGIN:
        return 403, {"ok": False, "error": "invalid_origin"}
    identity = _current_identity(host=host, cookie=cookie)
    if identity is None:
        return 401, {"ok": False, "error": "signin_required"}
    # role comes from signed, server-verified Next Session and configured
    # admin identity allowlist, not request body, query string or UI.
    if identity.get("role") != "admin":
        return 403, {"ok": False, "error": "platform_admin_required"}
    box = load_box()
    if method == "GET":
        pending = [p for item in box.get("pending_approvals", [])
                   if (p := _project(item)) is not None]
        history = [p for item in box.get("history", [])
                   if (p := _project(item)) is not None][:30]
        return 200, {"ok": True, "pending": pending, "history": history,
                     "scope": "platform.realm.review", "realm_provisioning": "not_automatic"}

    body = body or {}
    if set(body) != {"request_id", "decision"}:
        return 400, {"ok": False, "error": "unsupported_fields"}
    request_id = str(body.get("request_id") or "")
    decision = str(body.get("decision") or "").lower()
    if not request_id.startswith(_PREFIX) or len(request_id) != len(_PREFIX) + 32:
        return 400, {"ok": False, "error": "invalid_request_id"}
    if decision not in ("approve", "reject"):
        return 400, {"ok": False, "error": "invalid_decision"}
    pending = next((item for item in box.get("pending_approvals", [])
                    if item.get("id") == request_id and _project(item) is not None), None)
    if pending is None:
        existing = next((item for item in box.get("history", [])
                         if item.get("id") == request_id and _project(item) is not None), None)
        if existing is not None:
            return 409, {"ok": False, "error": "already_decided", "status": existing.get("status")}
        return 404, {"ok": False, "error": "request_not_found"}
    reviewer_digest = hashlib.sha256(
        (identity["provider"] + "\\x00" + identity["subject"]).encode()
    ).hexdigest()
    if pending.get("actor") == "oauth-account:" + reviewer_digest[:16]:
        return 403, {"ok": False, "error": "self_review_forbidden"}
    # Stable hashed identity avoids leaking a user's provider subject in
    # governance history or the public response.
    reviewer = hashlib.sha256(
        (identity["provider"] + "\x00" + identity["subject"]).encode()
    ).hexdigest()[:16]
    result = resolve_approval(request_id, decision, approver="platform-oauth:" + reviewer)
    if not result.get("success"):
        return 409, {"ok": False, "error": "review_conflict"}
    return 200, {
        "ok": True, "request_id": request_id,
        "status": result["status"],
        "realm_provisioning": "pending" if result["status"] == "APPROVED" else "not_allowed",
        "membership_granted": False,
    }
