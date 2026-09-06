from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock

from .contracts import SocialRequest, WRITE_OPERATIONS
from .credentials import AccountBinding, CredentialVault
from .governance import RuntimeWriteAcceptance


class FileCredentialVault(CredentialVault):
    """Runtime-owned credential persistence.

    Tokens are stored only inside the runtime host in a mode-0600 JSON file.
    Product-facing APIs expose AccountBinding values but never this file or token
    material. The file format is deliberately private to the runtime.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()
        self._ensure()

    def _ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"bindings": {}}, handle)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _load(self) -> dict:
        self._ensure()
        with self.path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict) or not isinstance(value.get("bindings"), dict):
            raise RuntimeError("social_credential_store_invalid")
        return value

    def _save(self, value: dict) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def get_binding(self, binding_id: str) -> AccountBinding | None:
        with self._lock:
            item = self._load()["bindings"].get(binding_id)
            if not isinstance(item, dict):
                return None
            return AccountBinding(
                binding_id=binding_id,
                product_id=str(item.get("product_id") or ""),
                platform=str(item.get("platform") or ""),
                provider_account_id=str(item.get("provider_account_id") or ""),
                username=(str(item.get("username")) if item.get("username") is not None else None),
            )

    def get_access_token(self, binding_id: str) -> str:
        with self._lock:
            item = self._load()["bindings"].get(binding_id)
            token = str(item.get("access_token") or "") if isinstance(item, dict) else ""
            if not token:
                raise RuntimeError("social_credential_unavailable")
            return token

    def bind(self, binding: AccountBinding, access_token: str) -> None:
        token = str(access_token or "").strip()
        if not token:
            raise ValueError("social_access_token_required")
        with self._lock:
            value = self._load()
            value["bindings"][binding.binding_id] = {
                "product_id": binding.product_id,
                "platform": binding.platform,
                "provider_account_id": binding.provider_account_id,
                "username": binding.username,
                "access_token": token,
            }
            self._save(value)

    def disconnect(self, binding_id: str) -> None:
        with self._lock:
            value = self._load()
            value["bindings"].pop(binding_id, None)
            self._save(value)


@dataclass(frozen=True)
class OneShotAcceptance:
    acceptance: RuntimeWriteAcceptance
    write_intent_id: str


class OneShotAcceptanceStore:
    """Process-local, single-consume write authority.

    Issuance belongs to the runtime control-plane, never the product endpoint.
    Exact product/platform/operation/account/write-intent matching is required.
    """

    def __init__(self) -> None:
        self._items: dict[str, OneShotAcceptance] = {}
        self._lock = RLock()

    def issue(self, request: SocialRequest) -> str:
        request.validate()
        if request.operation not in WRITE_OPERATIONS:
            raise ValueError("write_operation_required")
        if not request.account_binding_id or not request.write_intent_id:
            raise ValueError("exact_write_scope_required")
        acceptance_id = secrets.token_urlsafe(24)
        acceptance = RuntimeWriteAcceptance(
            acceptance_id=acceptance_id,
            product_id=request.product_id,
            platform=request.platform,
            operations=frozenset({request.operation}),
            account_binding_ids=frozenset({request.account_binding_id}),
        )
        with self._lock:
            self._items[acceptance_id] = OneShotAcceptance(acceptance, request.write_intent_id)
        return acceptance_id

    def consume(self, acceptance_id: str, request: SocialRequest) -> RuntimeWriteAcceptance:
        with self._lock:
            item = self._items.pop(str(acceptance_id or ""), None)
        if item is None:
            raise PermissionError("social_write_acceptance_invalid_or_consumed")
        if item.write_intent_id != request.write_intent_id:
            raise PermissionError("social_write_intent_mismatch")
        acceptance = item.acceptance
        if (
            acceptance.product_id != request.product_id
            or acceptance.platform != request.platform
            or request.operation not in acceptance.operations
            or request.account_binding_id not in acceptance.account_binding_ids
        ):
            raise PermissionError("social_write_acceptance_scope_mismatch")
        return acceptance
