from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentos_node.social.contracts import SocialRequest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.runtime_http import BrowserContextStore, ProductRegistration, ProductRegistry, SocialRuntime
from agentos_node.social.runtime_storage import FileCredentialVault, OneShotAcceptanceStore
from agentos_node.social.threads import ThreadsCapability, ThreadsProviderConfig, ThreadsProviderTransport


class FakeThreadsTransport(ThreadsProviderTransport):
    def __init__(self, configured: bool = True) -> None:
        self._configured_value = configured
        self.published = []

    def config(self) -> ThreadsProviderConfig:
        if not self._configured_value:
            from agentos_node.social.threads import ThreadsProviderError
            raise ThreadsProviderError("threads_oauth_not_configured")
        return ThreadsProviderConfig("app", "secret", "https://runtime.example/v1/social/oauth/threads/callback")

    def authorization_url(self, state: str) -> str:
        return f"https://threads.example/oauth?state={state}"

    def exchange_code(self, code: str) -> str:
        assert code == "provider-code"
        return "provider-token"

    def identity(self, token: str):
        assert token == "provider-token"
        return {"id": "42", "username": "cat"}

    def api(self, path: str, *, token: str, method: str = "GET", params=None):
        assert token == "provider-token"
        self.published.append((path, method, params))
        return {"id": "thread-1"}

    def revoke(self, token: str) -> None:
        return None


def registry() -> ProductRegistry:
    return ProductRegistry({
        "leopardcat-tarot": ProductRegistration(
            "leopardcat-tarot", "product-key", "https://tarot.example"
        )
    })


def runtime(configured: bool = True):
    vault = EphemeralCredentialVault()
    transport = FakeThreadsTransport(configured=configured)
    threads = ThreadsCapability(vault, transport)
    return SocialRuntime(
        products=registry(),
        threads=threads,
        acceptances=OneShotAcceptanceStore(),
        browser_contexts=BrowserContextStore(),
        control_token="control-key",
    ), vault, transport


def publish_request(**overrides):
    data = dict(
        product_id="leopardcat-tarot",
        platform="threads",
        operation="publish",
        account_binding_id="leopardcat-tarot:threads:42",
        target_account_id="42",
        primary_text="short intent",
        text_attachment={"plaintext": "full reading"},
        write_intent_id="intent-1",
    )
    data.update(overrides)
    return SocialRequest(**data)


def test_runtime_config_status_never_exposes_provider_values():
    rt, _vault, _transport = runtime(configured=True)
    value = rt.configured_status()
    assert value["threads"] == {"configured": True}
    text = repr(value).lower()
    assert "secret" not in text
    assert "provider-token" not in text


def test_product_registry_requires_exact_product_key():
    reg = registry()
    assert reg.authenticate("leopardcat-tarot", "product-key").product_id == "leopardcat-tarot"
    with pytest.raises(PermissionError, match="auth_failed"):
        reg.authenticate("leopardcat-tarot", "wrong")
    with pytest.raises(PermissionError, match="not_registered"):
        reg.authenticate("vendor-reputation-service", "product-key")


def test_oauth_callback_is_single_use_and_browser_session_bound():
    rt, vault, _transport = runtime()
    request = SocialRequest(
        product_id="leopardcat-tarot",
        platform="threads",
        operation="connect",
        return_to="/reading/1",
    )
    started = rt.connect(request)
    browser_session_id = started["browser_session_id"]
    state = started["authorization_url"].split("state=", 1)[1]

    with pytest.raises(PermissionError, match="browser_session_mismatch"):
        rt.complete_connect(state=state, code="provider-code", browser_session_id="other-browser")
    with pytest.raises(PermissionError, match="invalid_or_consumed"):
        rt.complete_connect(state=state, code="provider-code", browser_session_id=browser_session_id)
    assert vault.get_binding("leopardcat-tarot:threads:42") is None


def test_realistic_oauth_completion_returns_binding_not_token():
    rt, vault, _transport = runtime()
    request = SocialRequest(
        product_id="leopardcat-tarot",
        platform="threads",
        operation="connect",
        return_to="/reading/1",
    )
    started = rt.connect(request)
    state = started["authorization_url"].split("state=", 1)[1]
    location, result = rt.complete_connect(
        state=state,
        code="provider-code",
        browser_session_id=started["browser_session_id"],
    )
    assert location.startswith("https://tarot.example/reading/1")
    assert result["binding_id"] == "leopardcat-tarot:threads:42"
    assert result["account"]["provider_account_id"] == "42"
    assert "token" not in repr(result).lower()
    assert vault.get_access_token(result["binding_id"]) == "provider-token"


def test_publish_requires_control_issued_exact_one_shot_acceptance():
    rt, vault, transport = runtime()
    request = publish_request()
    vault.bind(AccountBinding(request.account_binding_id, request.product_id, "threads", "42", "cat"), "provider-token")

    with pytest.raises(PermissionError, match="invalid_or_consumed"):
        rt.execute_write(request, "missing")

    issued = rt.issue_acceptance(request, "control-key")
    receipt = rt.execute_write(request, issued["acceptance_id"])
    assert receipt["ok"] is True
    assert receipt["platform_object_id"] == "thread-1"
    assert transport.published[0][2]["text_attachment"] == '{"plaintext":"full reading"}'

    with pytest.raises(PermissionError, match="invalid_or_consumed"):
        rt.execute_write(request, issued["acceptance_id"])


def test_acceptance_cannot_be_reused_for_different_write_intent():
    rt, vault, _transport = runtime()
    original = publish_request()
    vault.bind(AccountBinding(original.account_binding_id, original.product_id, "threads", "42", "cat"), "provider-token")
    issued = rt.issue_acceptance(original, "control-key")
    changed = publish_request(write_intent_id="intent-2")
    with pytest.raises(PermissionError, match="write_intent_mismatch"):
        rt.execute_write(changed, issued["acceptance_id"])
    with pytest.raises(PermissionError, match="invalid_or_consumed"):
        rt.execute_write(original, issued["acceptance_id"])


def test_control_token_is_independent_from_product_auth():
    rt, _vault, _transport = runtime()
    with pytest.raises(PermissionError, match="control_auth_failed"):
        rt.issue_acceptance(publish_request(), "product-key")


def test_file_vault_persists_runtime_secret_only_and_mode_is_private(tmp_path: Path):
    path = tmp_path / "social" / "credentials.json"
    vault = FileCredentialVault(path)
    binding = AccountBinding("p:threads:42", "p", "threads", "42", "cat")
    vault.bind(binding, "SECRET-TOKEN")
    assert FileCredentialVault(path).get_binding(binding.binding_id) == binding
    assert FileCredentialVault(path).get_access_token(binding.binding_id) == "SECRET-TOKEN"
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
