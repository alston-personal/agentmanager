from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AccountBinding:
    binding_id: str
    product_id: str
    platform: str
    provider_account_id: str
    username: str | None = None


class CredentialVault(Protocol):
    """Runtime-only secret boundary. Implementations must not serialize secrets into receipts."""

    def get_binding(self, binding_id: str) -> AccountBinding | None: ...
    def get_access_token(self, binding_id: str) -> str: ...
    def bind(self, binding: AccountBinding, access_token: str) -> None: ...
    def disconnect(self, binding_id: str) -> None: ...


class EphemeralCredentialVault:
    """Reference implementation: process-memory only; restart disconnects all accounts."""

    def __init__(self) -> None:
        self._bindings: dict[str, AccountBinding] = {}
        self._tokens: dict[str, str] = {}

    def get_binding(self, binding_id: str) -> AccountBinding | None:
        return self._bindings.get(binding_id)

    def get_access_token(self, binding_id: str) -> str:
        token = self._tokens.get(binding_id, "")
        if not token:
            raise RuntimeError("social_credential_unavailable")
        return token

    def bind(self, binding: AccountBinding, access_token: str) -> None:
        token = str(access_token or "").strip()
        if not token:
            raise ValueError("social_access_token_required")
        self._bindings[binding.binding_id] = binding
        self._tokens[binding.binding_id] = token

    def disconnect(self, binding_id: str) -> None:
        self._tokens.pop(binding_id, None)
        self._bindings.pop(binding_id, None)
