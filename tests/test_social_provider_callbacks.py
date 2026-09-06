from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest

from agentos_node.social.credentials import AccountBinding
from agentos_node.social.provider_callbacks import ThreadsLifecycleCallbacks, verify_signed_request
from agentos_node.social.runtime_storage import FileCredentialVault
from agentos_node.social.threads import ThreadsProviderConfig, ThreadsProviderTransport


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def signed_request(payload: dict, secret: str = "app-secret") -> str:
    encoded_payload = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{b64url(signature)}.{encoded_payload}"


def transport() -> ThreadsProviderTransport:
    return ThreadsProviderTransport(
        lambda: ThreadsProviderConfig(
            app_id="app-id",
            app_secret="app-secret",
            redirect_uri="https://studio.milkcat.org/dashboard/api/social/v1/social/oauth/threads/callback",
        )
    )


def callbacks(tmp_path: Path):
    vault = FileCredentialVault(tmp_path / "credentials.json")
    cb = ThreadsLifecycleCallbacks(
        vault=vault,
        transport=transport(),
        public_base="https://studio.milkcat.org/dashboard/api/social",
    )
    return cb, vault


def test_signed_request_requires_valid_hmac_sha256():
    value = signed_request({"algorithm": "HMAC-SHA256", "user_id": "42"})
    assert verify_signed_request(value, "app-secret")["user_id"] == "42"
    with pytest.raises(PermissionError, match="signature_invalid"):
        verify_signed_request(value, "wrong-secret")


def test_deauthorize_removes_all_local_bindings_for_provider_account(tmp_path: Path):
    cb, vault = callbacks(tmp_path)
    vault.bind(AccountBinding("p1:threads:42", "p1", "threads", "42", "cat"), "TOKEN-1")
    vault.bind(AccountBinding("p2:threads:42", "p2", "threads", "42", "cat"), "TOKEN-2")
    vault.bind(AccountBinding("p1:threads:99", "p1", "threads", "99", "other"), "TOKEN-3")

    result = cb.deauthorize(signed_request({"algorithm": "HMAC-SHA256", "user_id": "42"}))

    assert result == {
        "schema": "agentos.social-provider-deauthorization/v1",
        "ok": True,
        "platform": "threads",
        "bindings_removed": 2,
    }
    assert vault.get_binding("p1:threads:42") is None
    assert vault.get_binding("p2:threads:42") is None
    assert vault.get_binding("p1:threads:99") is not None
    assert "TOKEN" not in repr(result)


def test_data_deletion_removes_binding_and_returns_provider_confirmation(tmp_path: Path):
    cb, vault = callbacks(tmp_path)
    vault.bind(AccountBinding("p:threads:42", "p", "threads", "42", "cat"), "SECRET-TOKEN")

    result = cb.data_deletion(signed_request({"algorithm": "HMAC-SHA256", "user_id": "42"}))

    assert vault.get_binding("p:threads:42") is None
    assert result["confirmation_code"]
    assert result["url"].startswith(
        "https://studio.milkcat.org/dashboard/api/social/v1/social/webhooks/threads/data-deletion/status?code="
    )
    assert "SECRET-TOKEN" not in repr(result)


def test_invalid_signature_does_not_delete_binding(tmp_path: Path):
    cb, vault = callbacks(tmp_path)
    vault.bind(AccountBinding("p:threads:42", "p", "threads", "42", "cat"), "SECRET-TOKEN")
    forged = signed_request({"algorithm": "HMAC-SHA256", "user_id": "42"}, secret="forged")

    with pytest.raises(PermissionError, match="signature_invalid"):
        cb.data_deletion(forged)

    assert vault.get_binding("p:threads:42") is not None
