from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from agentos_node.social.contracts import SocialRequest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.runtime_http import (
    BrowserContextStore,
    BrowserHandoffStore,
    ConnectionResultStore,
    ProductRegistration,
    ProductRegistry,
    SocialRuntime,
)
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


def runtime(
    configured: bool = True,
    *,
    browser_handoffs: BrowserHandoffStore | None = None,
    connection_results: ConnectionResultStore | None = None,
):
    vault = EphemeralCredentialVault()
    transport = FakeThreadsTransport(configured=configured)
    threads = ThreadsCapability(vault, transport)
    return SocialRuntime(
        products=registry(),
        threads=threads,
        acceptances=OneShotAcceptanceStore(),
        browser_contexts=BrowserContextStore(),
        browser_handoffs=browser_handoffs,
        connection_results=connection_results,
        control_token="control-key",
        public_base="https://studio.milkcat.org/dashboard/api/social",
    ), vault, transport


def connect_request():
    return SocialRequest(
        product_id="leopardcat-tarot",
        platform="threads",
        operation="connect",
        return_to="/reading/1",
    )


def status_request(connection_id: str):
    return SocialRequest(
        product_id="leopardcat-tarot",
        platform="threads",
        operation="status",
        object_id=connection_id,
    )


def handoff_ticket(value: dict[str, object]) -> str:
    parsed = urlsplit(str(value["browser_start_url"]))
    return parse_qs(parsed.query)["ticket"][0]


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


def test_product_connect_returns_opaque_handoff_and_connection_id_only():
    rt, _vault, _transport = runtime()
    started = rt.connect(connect_request())
    assert started["schema"] == "agentos.social-browser-handoff/v1"
    assert started["expires_in"] == 300
    assert started["connection_id"]
    assert started["browser_start_url"].startswith(
        "https://studio.milkcat.org/dashboard/api/social/v1/social/oauth/threads/start?ticket="
    )
    text = repr(started).lower()
    assert "threads.example" not in text
    assert "product-key" not in text
    assert "secret" not in text
    assert "token" not in text
    assert "state=" not in text


def test_browser_handoff_is_single_use_before_provider_oauth_state_exists():
    rt, _vault, _transport = runtime()
    ticket = handoff_ticket(rt.connect(connect_request()))
    authorization_url, browser_session_id = rt.begin_browser_connect(ticket)
    assert authorization_url.startswith("https://threads.example/oauth?state=")
    assert browser_session_id
    with pytest.raises(PermissionError, match="handoff_invalid_or_expired"):
        rt.begin_browser_connect(ticket)


def test_browser_handoff_expires_fail_closed():
    rt, _vault, _transport = runtime(browser_handoffs=BrowserHandoffStore(ttl_seconds=0))
    ticket = handoff_ticket(rt.connect(connect_request()))
    with pytest.raises(PermissionError, match="handoff_invalid_or_expired"):
        rt.begin_browser_connect(ticket)


def test_oauth_callback_is_single_use_and_browser_session_bound():
    rt, vault, _transport = runtime()
    started = rt.connect(connect_request())
    ticket = handoff_ticket(started)
    authorization_url, browser_session_id = rt.begin_browser_connect(ticket)
    state = authorization_url.split("state=", 1)[1]

    with pytest.raises(PermissionError, match="browser_session_mismatch"):
        rt.complete_connect(state=state, code="provider-code", browser_session_id="other-browser")
    with pytest.raises(PermissionError, match="invalid_or_consumed"):
        rt.complete_connect(state=state, code="provider-code", browser_session_id=browser_session_id)
    assert vault.get_binding("leopardcat-tarot:threads:42") is None
    with pytest.raises(PermissionError, match="connection_result_invalid_or_expired"):
        rt.status(status_request(started["connection_id"]))


def test_oauth_completion_redirect_has_no_binding_and_product_redeems_result_once():
    rt, vault, _transport = runtime()
    started = rt.connect(connect_request())
    authorization_url, browser_session_id = rt.begin_browser_connect(handoff_ticket(started))
    state = authorization_url.split("state=", 1)[1]
    location, callback_result = rt.complete_connect(
        state=state,
        code="provider-code",
        browser_session_id=browser_session_id,
    )
    assert location.startswith("https://tarot.example/reading/1?social=connected")
    assert "binding=" not in location
    assert callback_result == {
        "schema": "agentos.social-oauth-complete/v1",
        "connected": True,
        "connection_id": started["connection_id"],
    }
    assert "token" not in repr(callback_result).lower()

    redeemed = rt.status(status_request(started["connection_id"]))
    assert redeemed["schema"] == "agentos.social-connection-result/v1"
    assert redeemed["binding_id"] == "leopardcat-tarot:threads:42"
    assert redeemed["account"] == {"provider_account_id": "42", "username": "cat"}
    assert "token" not in repr(redeemed).lower()
    assert vault.get_access_token(redeemed["binding_id"]) == "provider-token"
    with pytest.raises(PermissionError, match="connection_result_invalid_or_expired"):
        rt.status(status_request(started["connection_id"]))


def test_connection_result_product_scope_mismatch_consumes_fail_closed():
    store = ConnectionResultStore()
    store.complete(
        "connection-1",
        product_id="leopardcat-tarot",
        platform="threads",
        binding_id="leopardcat-tarot:threads:42",
        account={"provider_account_id": "42", "username": "cat"},
    )
    with pytest.raises(PermissionError, match="connection_result_scope_mismatch"):
        store.consume("connection-1", product_id="other-product", platform="threads")
    with pytest.raises(PermissionError, match="connection_result_invalid_or_expired"):
        store.consume("connection-1", product_id="leopardcat-tarot", platform="threads")


def test_connection_result_expires_fail_closed():
    store = ConnectionResultStore(ttl_seconds=0)
    store.complete(
        "connection-1",
        product_id="leopardcat-tarot",
        platform="threads",
        binding_id="leopardcat-tarot:threads:42",
        account={"provider_account_id": "42", "username": "cat"},
    )
    with pytest.raises(PermissionError, match="connection_result_invalid_or_expired"):
        store.consume("connection-1", product_id="leopardcat-tarot", platform="threads")


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
