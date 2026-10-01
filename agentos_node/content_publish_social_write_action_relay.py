"""Governed content.publish -> Shared Social Runtime write bridge.

This fixed Action Relay action accepts a narrow, typed content-social write request.
Provider/product/control credentials remain host-local. A persistent intent ledger
prevents blind duplicate publication across new Action Relay capsules.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from agentos_node.action_relay import ACTIONS, ActionRelayClient
from agentos_node import content_publish_social_action_relay as social_bootstrap


WRITE_ACTION = "agentos.content.social.write"
WRITE_CAPABILITY = "content.publish.social.write"
WRITE_SCHEMA = "agentos.content-social-write/v1"
DEFAULT_RELAY_ROOT = Path("/home/ubuntu/agent-data/runtime/action-relay")
INTENT_ROOT = Path("/home/ubuntu/agent-data/runtime/content-publish/intents")
SOCIAL_BASE = "http://127.0.0.1:8771"
_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_WRITE_INTENT_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,160}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_PROJECTS = {"zeus-writer"}
_ALLOWED_AUTHORITY = "approved-content-publish"


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _validate_request(raw: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema",
        "project_id",
        "platform",
        "account_ref",
        "operation",
        "primary_text",
        "image_url",
        "image_alt_text",
        "reply_to_id",
        "write_intent_id",
        "content_hash",
        "authority",
    }
    if set(raw) - allowed:
        raise ValueError("content_social_write_unsupported_field")
    if raw.get("schema") != WRITE_SCHEMA:
        raise ValueError("content_social_write_schema_invalid")
    project_id = str(raw.get("project_id") or "").strip()
    if not _PROJECT_RE.fullmatch(project_id) or project_id not in _ALLOWED_PROJECTS:
        raise ValueError("content_social_write_project_not_allowed")
    if raw.get("platform") != "threads":
        raise ValueError("content_social_write_platform_not_allowed")
    account_ref = str(raw.get("account_ref") or "").strip()
    # Resolve against source-owned configuration; unknown refs fail closed.
    social_bootstrap._load_account_config(account_ref)
    operation = str(raw.get("operation") or "").strip()
    if operation not in {"publish", "reply"}:
        raise ValueError("content_social_write_operation_not_allowed")
    primary_text = str(raw.get("primary_text") or "").strip()
    if not primary_text or len(primary_text) > 500:
        raise ValueError("content_social_write_primary_text_invalid")
    intent = str(raw.get("write_intent_id") or "").strip()
    if not _WRITE_INTENT_RE.fullmatch(intent):
        raise ValueError("content_social_write_intent_invalid")
    content_hash = str(raw.get("content_hash") or "").strip().lower()
    if not _HEX64_RE.fullmatch(content_hash):
        raise ValueError("content_social_write_content_hash_invalid")
    if str(raw.get("authority") or "") != _ALLOWED_AUTHORITY:
        raise PermissionError("content_social_write_authority_required")

    image_url = str(raw.get("image_url") or "").strip() or None
    image_alt_text = str(raw.get("image_alt_text") or "").strip() or None
    reply_to_id = str(raw.get("reply_to_id") or "").strip() or None
    if operation == "reply":
        if not reply_to_id:
            raise ValueError("content_social_write_reply_target_required")
        if image_url or image_alt_text:
            raise ValueError("content_social_write_reply_media_not_supported")
    else:
        if reply_to_id:
            raise ValueError("content_social_write_publish_reply_target_forbidden")
        if image_url:
            parsed = urlsplit(image_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
                or len(image_url) > 2048
            ):
                raise ValueError("content_social_write_image_url_invalid")
            if not image_alt_text or len(image_alt_text) > 1000:
                raise ValueError("content_social_write_image_alt_required")
        elif image_alt_text:
            raise ValueError("content_social_write_image_alt_without_image")

    return {
        "schema": WRITE_SCHEMA,
        "project_id": project_id,
        "platform": "threads",
        "account_ref": account_ref,
        "operation": operation,
        "primary_text": primary_text,
        "image_url": image_url,
        "image_alt_text": image_alt_text,
        "reply_to_id": reply_to_id,
        "write_intent_id": intent,
        "content_hash": content_hash,
        "authority": _ALLOWED_AUTHORITY,
    }


def _resolve_account(account_ref: str) -> dict[str, str]:
    registry = social_bootstrap._load_registry()
    item = registry.get("accounts", {}).get(account_ref)
    if not isinstance(item, dict):
        raise RuntimeError("content_social_write_account_binding_required")
    required = {
        "platform": "threads",
        "product_id": "content-publish",
    }
    for key, expected in required.items():
        if str(item.get(key) or "") != expected:
            raise RuntimeError("content_social_write_account_binding_scope_invalid")
    binding_id = str(item.get("binding_id") or "")
    provider_account_id = str(item.get("provider_account_id") or "")
    if not binding_id or not provider_account_id:
        raise RuntimeError("content_social_write_account_binding_incomplete")
    return {
        "binding_id": binding_id,
        "provider_account_id": provider_account_id,
        "username": str(item.get("username") or ""),
    }


def _control_token() -> str:
    env = social_bootstrap._parse_env(social_bootstrap.SOCIAL_ENV)
    token = str(env.get("AGENTOS_SOCIAL_CONTROL_TOKEN") or "")
    if not token:
        raise RuntimeError("content_social_control_token_unavailable")
    return token


def _post_json(
    path: str,
    payload: Mapping[str, Any],
    *,
    headers: Mapping[str, str],
    timeout: float = 20,
) -> tuple[int, dict[str, Any]]:
    data = _canonical_json(payload)
    req = urllib.request.Request(
        SOCIAL_BASE + path,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **dict(headers),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            return int(response.status), value
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except Exception:
            value = {"ok": False, "error": "runtime_http_error"}
        return int(exc.code), value
    except urllib.error.URLError as exc:
        raise RuntimeError("content_social_runtime_unreachable") from exc


def _intent_path(request: Mapping[str, Any]) -> Path:
    scope = {
        "project_id": request["project_id"],
        "platform": request["platform"],
        "account_ref": request["account_ref"],
        "write_intent_id": request["write_intent_id"],
    }
    return INTENT_ROOT / (_digest(scope) + ".json")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", dir=str(path.parent), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o660)
        os.replace(temp_name, path)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    try:
        os.chmod(path, 0o660)
    except OSError:
        pass


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise RuntimeError("content_social_intent_ledger_invalid")
    return value


def _public_receipt(
    request: Mapping[str, Any],
    *,
    status: str,
    account: Mapping[str, str],
    platform_object_id: str | None = None,
    permalink: str | None = None,
    deduplicated: bool = False,
    reconcile_required: bool = False,
    safe_to_retry: bool = False,
) -> dict[str, Any]:
    return {
        "schema": "agentos.content-publish-receipt/v1",
        "ok": status == "published",
        "capability": WRITE_CAPABILITY,
        "project_id": request["project_id"],
        "platform": "threads",
        "account_ref": request["account_ref"],
        "provider": "threads-social-runtime",
        "status": status,
        "operation": request["operation"],
        "write_intent_id": request["write_intent_id"],
        "content_hash": request["content_hash"],
        "platform_object_id": platform_object_id,
        "permalink": permalink,
        "username": account.get("username") or None,
        "deduplicated": bool(deduplicated),
        "reconcile_required": bool(reconcile_required),
        "safe_to_retry": bool(safe_to_retry),
        "credential_exposed": False,
    }


def execute_write(raw: Mapping[str, Any]) -> dict[str, Any]:
    request = _validate_request(raw)
    account = _resolve_account(request["account_ref"])
    path = _intent_path(request)
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    request_digest = _digest(request)

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        previous = _read_json(path)
        if previous is not None:
            if previous.get("request_digest") != request_digest:
                raise RuntimeError("content_social_write_intent_conflict")
            state = str(previous.get("state") or "")
            prior_receipt = previous.get("receipt")
            if state == "published" and isinstance(prior_receipt, dict):
                result = dict(prior_receipt)
                result["deduplicated"] = True
                return result
            if state in {"in_flight", "unknown"}:
                unknown = _public_receipt(
                    request,
                    status="unknown",
                    account=account,
                    reconcile_required=True,
                )
                _atomic_json(
                    path,
                    {
                        "schema": "agentos.content-social-intent-state/v1",
                        "state": "unknown",
                        "request_digest": request_digest,
                        "receipt": unknown,
                    },
                )
                return unknown
            if state == "safe_failure":
                # No provider write was attempted; same exact intent may retry.
                pass

        _atomic_json(
            path,
            {
                "schema": "agentos.content-social-intent-state/v1",
                "state": "in_flight",
                "request_digest": request_digest,
            },
        )

        social_request: dict[str, Any] = {
            "schema": "agentos.social-request/v1",
            "product_id": "content-publish",
            "platform": "threads",
            "operation": request["operation"],
            "account_binding_id": account["binding_id"],
            "target_account_id": account["provider_account_id"],
            "primary_text": request["primary_text"],
            "write_intent_id": request["write_intent_id"],
        }
        if request["operation"] == "reply":
            social_request["reply_to_id"] = request["reply_to_id"]
        elif request.get("image_url"):
            social_request["image_url"] = request["image_url"]
            social_request["image_alt_text"] = request["image_alt_text"]

        try:
            code, accepted = _post_json(
                "/internal/v1/social/acceptances",
                social_request,
                headers={"X-AgentOS-Control-Token": _control_token()},
            )
        except RuntimeError:
            failed = _public_receipt(
                request,
                status="authority_unavailable",
                account=account,
                safe_to_retry=True,
            )
            _atomic_json(
                path,
                {
                    "schema": "agentos.content-social-intent-state/v1",
                    "state": "safe_failure",
                    "request_digest": request_digest,
                    "receipt": failed,
                },
            )
            return failed

        acceptance_id = str(accepted.get("acceptance_id") or "")
        if code not in {200, 201} or not acceptance_id:
            failed = _public_receipt(
                request,
                status="authority_denied",
                account=account,
                safe_to_retry=True,
            )
            _atomic_json(
                path,
                {
                    "schema": "agentos.content-social-intent-state/v1",
                    "state": "safe_failure",
                    "request_digest": request_digest,
                    "receipt": failed,
                },
            )
            return failed

        endpoint = (
            "/v1/social/reply"
            if request["operation"] == "reply"
            else "/v1/social/publish"
        )
        try:
            code, provider_receipt = _post_json(
                endpoint,
                social_request,
                headers={
                    "X-AgentOS-Product-Key": social_bootstrap._product_key(
                        "content-publish"
                    ),
                    "X-AgentOS-Acceptance-ID": acceptance_id,
                },
            )
        except RuntimeError:
            code, provider_receipt = 0, {}

        if (
            code == 200
            and isinstance(provider_receipt, dict)
            and provider_receipt.get("ok") is True
        ):
            published = _public_receipt(
                request,
                status="published",
                account=account,
                platform_object_id=(
                    str(provider_receipt.get("platform_object_id") or "") or None
                ),
                permalink=(str(provider_receipt.get("permalink") or "") or None),
            )
            _atomic_json(
                path,
                {
                    "schema": "agentos.content-social-intent-state/v1",
                    "state": "published",
                    "request_digest": request_digest,
                    "receipt": published,
                },
            )
            return published

        # Acceptance was already issued and may have been consumed. A transport
        # failure here can straddle a provider side effect. Never blind-retry.
        unknown = _public_receipt(
            request,
            status="unknown",
            account=account,
            reconcile_required=True,
        )
        _atomic_json(
            path,
            {
                "schema": "agentos.content-social-intent-state/v1",
                "state": "unknown",
                "request_digest": request_digest,
                "receipt": unknown,
            },
        )
        return unknown


def _execute(params: dict[str, Any]) -> dict[str, Any]:
    if set(params) != {"request"} or not isinstance(params.get("request"), dict):
        raise ValueError("content-social write accepts only canonical request")
    return execute_write(dict(params["request"]))


if WRITE_ACTION in ACTIONS and ACTIONS[WRITE_ACTION] is not _execute:
    raise RuntimeError("content-social write action already registered differently")
ACTIONS[WRITE_ACTION] = _execute


class ContentPublishSocialWriteDispatcher:
    def __init__(self, root: str | Path = DEFAULT_RELAY_ROOT):
        self.root = Path(root)
        self.client = ActionRelayClient(self.root)

    def submit(self, *, request: Mapping[str, Any]) -> dict[str, Any]:
        canonical = _validate_request(request)
        capsule = self.client.submit(WRITE_ACTION, {"request": canonical})
        return {
            "schema": "agentos.content-social-write-submission/v1",
            "task_id": str(capsule["capsule_id"]),
            "action": WRITE_CAPABILITY,
            "state": "queued",
            "write_intent_id": canonical["write_intent_id"],
        }

    def inspect(self, task_id: str) -> dict[str, Any] | None:
        receipt = self.client.receipt(str(task_id))
        if receipt is None:
            return None
        if receipt.get("action") not in {None, WRITE_ACTION}:
            raise RuntimeError("content_social_write_receipt_action_mismatch")
        allowed = {
            "schema",
            "ok",
            "capability",
            "project_id",
            "platform",
            "account_ref",
            "provider",
            "status",
            "operation",
            "write_intent_id",
            "content_hash",
            "platform_object_id",
            "permalink",
            "username",
            "deduplicated",
            "reconcile_required",
            "safe_to_retry",
            "credential_exposed",
            "executor_user",
        }
        result = {key: receipt.get(key) for key in allowed if key in receipt}
        result["task_id"] = str(task_id)
        result["credential_exposed"] = False
        return result
