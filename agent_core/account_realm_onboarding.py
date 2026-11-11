"""Authenticated AgentOS account-to-Realm onboarding requests (no provisioning).

An OAuth session proves an account identity, not permission to access a
pre-existing Realm. Every account starts without Realm authority; the existing
operator approval box receives an explicit review request.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

from .approval_broker import park_approval, load_box
from .shared_auth_bridge import proxy_shared_auth_request

_BASE = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")) / "onboarding" / "realm-requests"
_REALM = re.compile(r"[a-z][a-z0-9-]{2,62}\Z")


class OnboardingError(ValueError):
    pass


def _current_identity(*, host: str, cookie: str | None) -> dict[str, str] | None:
    status, _, body = proxy_shared_auth_request(
        raw_path="/dashboard/api/auth/session", method="GET", host=host, cookie=cookie
    )
    if status != 200:
        return None
    try:
        session = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if session.get("loggedIn") is not True:
        return None
    provider = str(session.get("provider") or "").lower()
    subject = str(session.get("subject") or "")
    if provider not in {"google", "github", "facebook", "line"} or not subject or len(subject) > 256:
        return None
    display_name = str(session.get("username") or "").strip()[:128]
    return {"provider": provider, "subject": subject, "role": str(session.get("role") or "user"),
            "display_name": display_name}


def account_request(
    *,
    method: str,
    host: str,
    cookie: str | None,
    origin: str | None,
    body: dict[str, Any] | None = None,
    root: Path = _BASE,
) -> tuple[int, dict[str, Any]]:
    if host.lower().split(":")[0] != "agentos.milkcat.org":
        return 400, {"ok": False, "error": "invalid_site"}
    if method not in {"GET", "POST"}:
        return 405, {"ok": False, "error": "method_not_allowed"}
    if method == "POST" and origin != "https://agentos.milkcat.org":
        return 403, {"ok": False, "error": "invalid_origin"}
    identity = _current_identity(host=host, cookie=cookie)
    if not identity:
        return 401, {"ok": False, "error": "signin_required"}

    # Hash external-provider subject. No email, user display name or access
    # token is persisted in the operator-visible review box.
    digest = hashlib.sha256(
        (identity["provider"] + "\x00" + identity["subject"]).encode("utf-8")
    ).hexdigest()
    file = root / (digest + ".json")
    if file.exists():
        try:
            record = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return 503, {"ok": False, "error": "registration_unavailable"}
        # For existing requests created before applicant details were supported,
        # refresh the name only from the same verified OAuth identity. This
        # does not change the requested action, identity hash or grant rights.
        name = identity.get("display_name", "").strip()
        if name and not record.get("applicant_display_name"):
            record["applicant_display_name"] = name
            tmp = file.with_suffix(".tmp")
            try:
                with open(tmp, "x", encoding="utf-8") as fp:
                    json.dump(record, fp, ensure_ascii=False)
                    fp.write("\n")
                    fp.flush()
                    os.fsync(fp.fileno())
                os.replace(tmp, file)
            except FileExistsError:
                pass
            except OSError:
                tmp.unlink(missing_ok=True)
        # Distinguish governance decision from actual ONE provisioning.
        # Even an approved request grants no account-to-Realm membership.
        state = "pending_review"
        box = load_box()
        for item in box.get("history", []):
            if item.get("id") == record["request_id"] and item.get("action_type") == "realm.onboarding.request":
                if item.get("status") == "APPROVED":
                    state = "approved_pending_provisioning"
                elif item.get("status") == "REJECTED":
                    state = "rejected"
                break
        if state == "approved_pending_provisioning" and record.get("kind") == "create":
            from .realm_provisioning import owner_realm
            owned = owner_realm(identity)
            if owned is not None and owned["request_id"] == record["request_id"]:
                return 200, {
                    "ok": True, "state": "realm_initialized",
                    "kind": "create", "request_id": record["request_id"],
                    "realm_id": owned["realm_id"], "provisioned": True,
                    "one_runtime_attested": False,
                }
        return 200, {"ok": True, "state": state, "kind": record["kind"],
                     "request_id": record["request_id"], "realm_id": record.get("realm_id"),
                     "provisioned": False}

    if method == "GET":
        return 200, {"ok": True, "state": "not_requested", "role": identity["role"]}

    body = body or {}
    if set(body) - {"kind", "realm_id"}:
        return 400, {"ok": False, "error": "unsupported_fields"}
    kind = str(body.get("kind") or "")
    if kind not in {"create", "join"}:
        return 400, {"ok": False, "error": "invalid_kind"}
    realm_id = str(body.get("realm_id") or "").strip().lower()
    if kind == "create" and realm_id:
        return 400, {"ok": False, "error": "realm_id_not_allowed_for_creation"}
    if kind == "join" and not _REALM.fullmatch(realm_id):
        return 400, {"ok": False, "error": "invalid_realm_id"}
    request_id = "realm-onboarding-" + digest[:32]
    record = {
        "schema": "agentos.account-realm-onboarding/v1",
        "request_id": request_id,
        "actor": digest,
        "provider": identity["provider"],
        "applicant_display_name": identity.get("display_name", ""),
        "kind": kind,
        "realm_id": realm_id if kind == "join" else None,
        "state": "pending_review",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provisioned": False,
    }
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Atomically claim this identity and make retries idempotent.
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(record, fp)
                fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())
        except Exception:
            file.unlink(missing_ok=True)
            raise
        park_approval(
            approval_id=request_id,
            project_id="agentos-core",
            actor="oauth-account:" + digest[:16],
            title="AgentOS account Realm " + kind + " request",
            action_type="realm.onboarding.request",
            payload={"schema": record["schema"], "request_id": request_id, "kind": kind,
                     "realm_id": record["realm_id"], "provisioned": False},
            next_unblocked_task="owner review and separate ONE Realm provisioning",
        )
    except FileExistsError:
        return account_request(method="GET", host=host, cookie=cookie, origin=None, root=root)
    except (OSError, ValueError):
        return 503, {"ok": False, "error": "registration_unavailable"}

    # An approval request is NOT a Realm membership or provisioning receipt.
    return 202, {"ok": True, "state": "pending_review", "kind": kind,
                 "realm_id": record["realm_id"], "request_id": request_id}
