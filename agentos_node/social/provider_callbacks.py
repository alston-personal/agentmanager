from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Any

from .runtime_storage import FileCredentialVault
from .threads import ThreadsProviderConfig, ThreadsProviderError, ThreadsProviderTransport


def _b64url_decode(value: str) -> bytes:
    value = str(value or "").strip()
    if not value:
        raise ValueError("threads_signed_request_invalid")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except Exception as exc:
        raise ValueError("threads_signed_request_invalid") from exc


def verify_signed_request(signed_request: str, app_secret: str) -> dict[str, Any]:
    secret = str(app_secret or "")
    if not secret:
        raise ThreadsProviderError("threads_oauth_not_configured")
    try:
        encoded_sig, encoded_payload = str(signed_request or "").split(".", 1)
    except ValueError as exc:
        raise ValueError("threads_signed_request_invalid") from exc
    actual_sig = _b64url_decode(encoded_sig)
    expected_sig = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(actual_sig, expected_sig):
        raise PermissionError("threads_signed_request_signature_invalid")
    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("threads_signed_request_payload_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("threads_signed_request_payload_invalid")
    algorithm = str(payload.get("algorithm") or "HMAC-SHA256").upper()
    if algorithm != "HMAC-SHA256":
        raise PermissionError("threads_signed_request_algorithm_invalid")
    return payload


@dataclass(frozen=True)
class ThreadsLifecycleCallbacks:
    vault: FileCredentialVault
    transport: ThreadsProviderTransport
    public_base: str

    def _config(self) -> ThreadsProviderConfig:
        return self.transport.config()

    def _payload(self, signed_request: str) -> dict[str, Any]:
        return verify_signed_request(signed_request, self._config().app_secret)

    def _provider_user_id(self, payload: dict[str, Any]) -> str:
        user_id = str(payload.get("user_id") or payload.get("id") or "").strip()
        if not user_id:
            raise ValueError("threads_signed_request_user_id_required")
        return user_id

    def deauthorize(self, signed_request: str) -> dict[str, Any]:
        payload = self._payload(signed_request)
        user_id = self._provider_user_id(payload)
        removed = self.vault.disconnect_provider_account(platform="threads", provider_account_id=user_id)
        return {
            "schema": "agentos.social-provider-deauthorization/v1",
            "ok": True,
            "platform": "threads",
            "bindings_removed": removed,
        }

    def data_deletion(self, signed_request: str) -> dict[str, Any]:
        payload = self._payload(signed_request)
        user_id = self._provider_user_id(payload)
        removed = self.vault.disconnect_provider_account(platform="threads", provider_account_id=user_id)
        confirmation_code = secrets.token_urlsafe(18)
        base = self.public_base.rstrip("/")
        status_url = (
            base
            + "/v1/social/webhooks/threads/data-deletion/status?"
            + urllib.parse.urlencode({"code": confirmation_code})
        )
        return {
            "url": status_url,
            "confirmation_code": confirmation_code,
            "bindings_removed": removed,
        }
