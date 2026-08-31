from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class CredentialBinding:
    ref: str
    env_var: str
    platform: str
    account_hint: Optional[str] = None


DEFAULT_BINDINGS: Mapping[str, CredentialBinding] = {
    "threads/default": CredentialBinding(
        ref="threads/default",
        env_var="SOC_THREADS_TOKEN",
        platform="threads",
        account_hint="default Threads identity",
    ),
    "facebook/default": CredentialBinding(
        ref="facebook/default",
        env_var="SOC_FB_TOKEN",
        platform="facebook",
        account_hint="default Facebook identity",
    ),
    "instagram/default": CredentialBinding(
        ref="instagram/default",
        env_var="SOC_FB_TOKEN",
        platform="instagram",
        account_hint="default Instagram business identity",
    ),
}


class EnvironmentCredentialResolver:
    """Resolve a logical credential ref locally without exposing it in receipts."""

    def __init__(self, bindings: Mapping[str, CredentialBinding] = DEFAULT_BINDINGS):
        self._bindings = dict(bindings)

    def binding(self, credential_ref: str) -> CredentialBinding:
        try:
            return self._bindings[credential_ref]
        except KeyError as exc:
            raise KeyError(f"unknown credential_ref: {credential_ref}") from exc

    def resolve(self, credential_ref: str) -> str:
        binding = self.binding(credential_ref)
        value = os.environ.get(binding.env_var, "").strip()
        if not value:
            raise RuntimeError(f"credential unavailable: {credential_ref}")
        return value

    def present(self, credential_ref: str) -> bool:
        binding = self.binding(credential_ref)
        return bool(os.environ.get(binding.env_var, "").strip())
