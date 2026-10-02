"""Ubuntu-local preaccepted Threads executor for content.publish.

No Action Relay action is registered here. A one-shot Social Runtime acceptance
is authority material and must not be persisted in the shared relay spool.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import urllib.error
import urllib.request

from runtime_core.content_publish import build_publish_receipt
from runtime_core.content_publish_social import (
    build_threads_social_request,
    social_request_payload,
)

SOCIAL_BASE = "http://127.0.0.1:8771"
SOCIAL_PRODUCT_DIR = Path("/home/ubuntu/.config/agentos/social-products")
ACCOUNT_REGISTRY = Path("/home/ubuntu/.config/agentos/content-publish/accounts.json")
MAX_RESPONSE_BYTES = 64 * 1024


def _parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError("content_publish_social_product_registration_missing")
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw or raw.lstrip().startswith("#"):
            continue
        key, value = raw.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _product_key() -> str:
    env = _parse_env(SOCIAL_PRODUCT_DIR / "content-publish.env")
    if env.get("AGENTOS_SOCIAL_PRODUCT_ID") != "content-publish":
        raise RuntimeError("content_publish_social_product_identity_mismatch")
    value = str(env.get("AGENTOS_SOCIAL_PRODUCT_KEY") or "")
    if not value:
        raise RuntimeError("content_publish_social_product_key_missing")
    return value


def _account(account_ref: str) -> dict[str, Any]:
    if not ACCOUNT_REGISTRY.is_file():
        raise RuntimeError("content_publish_social_account_registry_missing")
    value = json.loads(ACCOUNT_REGISTRY.read_text(encoding="utf-8"))
    if value.get("schema") != "agentos.content-publish-account-registry/v1":
        raise RuntimeError("content_publish_social_account_registry_invalid")
    item = (value.get("accounts") or {}).get(str(account_ref or ""))
    if not isinstance(item, dict):
        raise RuntimeError("content_publish_social_account_not_bound")
    return {"account_ref": str(account_ref), **item}


def _execute_runtime(
    social_request: Mapping[str, Any],
    *,
    acceptance_id: str,
    product_key: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    acceptance = str(acceptance_id or "").strip()
    if not acceptance:
        raise PermissionError("content_publish_social_acceptance_required")
    body = json.dumps(social_request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        SOCIAL_BASE + "/v1/social/publish",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-AgentOS-Product-Key": product_key,
            "X-AgentOS-Acceptance-ID": acceptance,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # HTTP rejection is terminal for this attempt and does not reveal either
        # product key or acceptance material.
        raise RuntimeError(f"content_publish_social_runtime_http_{int(exc.code)}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        # Request delivery may have happened. Never blind-retry the same write.
        raise RuntimeError("content_publish_social_execution_outcome_unknown") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("content_publish_social_response_too_large")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("content_publish_social_response_invalid")
    return value


def execute_preaccepted_threads(
    publish_request: Mapping[str, Any],
    artifact: Mapping[str, Any],
    *,
    acceptance_id: str,
    account: Mapping[str, Any] | None = None,
    media_resolutions: Mapping[str, Mapping[str, Any]] | None = None,
    runtime_call=_execute_runtime,
) -> dict[str, Any]:
    """Execute only with a separately-issued exact one-shot acceptance.

    This function does not issue acceptance and does not treat the request's
    authority string as runtime authorization.
    """
    account_item = dict(account) if account is not None else _account(str(publish_request.get("account_ref") or ""))
    projected = build_threads_social_request(
        publish_request,
        artifact,
        account_item,
        media_resolutions=media_resolutions,
    )
    social_payload = social_request_payload(projected)

    try:
        result = runtime_call(
            social_payload,
            acceptance_id=acceptance_id,
            product_key=_product_key(),
        )
    except RuntimeError as exc:
        status = "UNKNOWN" if str(exc) == "content_publish_social_execution_outcome_unknown" else "FAILED"
        return build_publish_receipt(
            platform="threads",
            provider="threads-social-runtime",
            account_ref=str(publish_request.get("account_ref") or ""),
            status=status,
            write_intent_id=str(publish_request.get("write_intent_id") or "") or None,
            artifact=artifact,
            result={
                "error_code": str(exc),
                "reconcile_required": status == "UNKNOWN",
                "public_publish_performed": None if status == "UNKNOWN" else False,
            },
        )

    ok = result.get("ok") is True
    return build_publish_receipt(
        platform="threads",
        provider="threads-social-runtime",
        account_ref=str(publish_request.get("account_ref") or ""),
        status="PUBLISHED" if ok else "FAILED",
        write_intent_id=str(publish_request.get("write_intent_id") or "") or None,
        artifact=artifact,
        result={
            "platform_object_id": result.get("platform_object_id"),
            "permalink": result.get("permalink"),
            "error_code": result.get("error_code"),
            "public_publish_performed": bool(ok),
            "reconcile_required": False,
            "media_resolution": projected.get("media_resolution") or [],
        },
    )
