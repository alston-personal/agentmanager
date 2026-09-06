from __future__ import annotations

import pytest

from agentos_node.social.contracts import SocialReceipt, SocialRequest
from agentos_node.social.credentials import AccountBinding, EphemeralCredentialVault
from agentos_node.social.governance import RuntimeWriteAcceptance, SocialWriteGate
from agentos_node.social.oauth import OAuthStateStore, sanitized_oauth_return
from agentos_node.social.registry import default_registry


def publish_request(**overrides):
    data = dict(
        product_id="leopardcat-tarot",
        platform="threads",
        operation="publish",
        account_binding_id="leopardcat-tarot:threads:42",
        target_account_id="42",
        primary_text="short share intent",
        text_attachment="full interpretation",
        write_intent_id="intent-1",
    )
    data.update(overrides)
    return SocialRequest(**data)


def test_write_fails_closed_without_runtime_acceptance():
    with pytest.raises(PermissionError, match="social_write_not_runtime_accepted"):
        SocialWriteGate().authorize(publish_request())


def test_write_acceptance_is_exact_product_platform_operation_and_account():
    request = publish_request()
    accepted = RuntimeWriteAcceptance("accept-1", "leopardcat-tarot", "threads", frozenset({"publish"}), frozenset({request.account_binding_id}))
    SocialWriteGate().authorize(request, accepted)
    with pytest.raises(PermissionError):
        SocialWriteGate().authorize(request, RuntimeWriteAcceptance("accept-2", "vendor-reputation-service", "threads", frozenset({"publish"}), frozenset({request.account_binding_id})))


def test_receipt_recursively_rejects_secret_fields():
    receipt = SocialReceipt("p", "threads", "status", True, "a", "b", "social.threads.status", result={"nested": {"access_token": "SECRET"}})
    with pytest.raises(ValueError, match="secret-bearing"):
        receipt.to_dict()


def test_ephemeral_vault_never_puts_token_in_binding():
    vault = EphemeralCredentialVault()
    binding = AccountBinding("p:threads:42", "p", "threads", "42", "cat")
    vault.bind(binding, "SECRET-TOKEN")
    assert vault.get_binding(binding.binding_id) == binding
    assert "SECRET" not in repr(binding)
    vault.disconnect(binding.binding_id)
    assert vault.get_binding(binding.binding_id) is None


def test_oauth_state_is_single_use_and_product_scoped():
    store = OAuthStateStore()
    issued = store.issue(product_id="leopardcat-tarot", browser_session_id="s1", platform="threads", return_to="/reading/1")
    with pytest.raises(PermissionError, match="scope_mismatch"):
        store.consume(state=issued.state, product_id="vendor-reputation-service", browser_session_id="s1", platform="threads")
    # Scope failure consumes the state instead of leaving a replayable credential flow.
    with pytest.raises(PermissionError, match="invalid_or_expired"):
        store.consume(state=issued.state, product_id="leopardcat-tarot", browser_session_id="s1", platform="threads")


def test_oauth_return_never_contains_provider_code_or_token():
    value = sanitized_oauth_return("/reading/1", connected=True, binding_id="p:threads:42")
    assert "connected" in value
    assert "code=" not in value
    assert "token" not in value


def test_registry_declares_threads_facebook_instagram_and_no_write_is_runtime_accepted():
    specs = default_registry.list()
    assert {item.platform for item in specs} == {"threads", "facebook", "instagram"}
    assert any(item.name == "social.threads.public_post.read" for item in specs)
    assert all(not item.runtime_accepted for item in specs if item.write)
