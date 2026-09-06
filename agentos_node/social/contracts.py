from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


WRITE_OPERATIONS = frozenset({"publish", "reply", "disconnect"})
READ_OPERATIONS = frozenset({"status", "identity.read", "post.read", "replies.read", "public_post.read", "connect"})
SUPPORTED_OPERATIONS = READ_OPERATIONS | WRITE_OPERATIONS
FORBIDDEN_RECEIPT_KEYS = frozenset({
    "access_token", "refresh_token", "token", "app_secret", "client_secret",
    "authorization", "authorization_code", "code", "credential", "credentials",
    "cookie", "set_cookie", "oauth_url", "authorization_url",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _assert_secret_free(value: Any, path: str = "receipt") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_RECEIPT_KEYS or normalized.endswith("_token") or normalized.endswith("_secret"):
                raise ValueError(f"secret-bearing receipt field forbidden: {path}.{key}")
            _assert_secret_free(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_secret_free(item, f"{path}[{index}]")


@dataclass(frozen=True)
class SocialRequest:
    """Provider-neutral request presented by a product to the shared social runtime."""

    product_id: str
    platform: str
    operation: str
    account_binding_id: str | None = None
    target_account_id: str | None = None
    primary_text: str | None = None
    text_attachment: dict[str, str] | None = None
    object_id: str | None = None
    reply_to_id: str | None = None
    return_to: str | None = None
    write_intent_id: str | None = None
    schema: str = "agentos.social-request/v1"

    def validate(self) -> "SocialRequest":
        if self.schema != "agentos.social-request/v1":
            raise ValueError("unsupported_social_request_schema")
        if not self.product_id.strip():
            raise ValueError("product_id_required")
        if self.platform not in {"threads", "facebook", "instagram"}:
            raise ValueError("unsupported_social_platform")
        if self.operation not in SUPPORTED_OPERATIONS:
            raise ValueError("unsupported_social_operation")
        if self.operation in WRITE_OPERATIONS and not self.write_intent_id:
            raise ValueError("explicit_write_intent_required")
        if self.operation in {"publish", "reply"}:
            if not self.account_binding_id or not self.target_account_id:
                raise ValueError("explicit_target_account_required")
            if not str(self.primary_text or "").strip():
                raise ValueError("primary_text_required")
            if self.text_attachment is not None:
                if not isinstance(self.text_attachment, dict) or not str(self.text_attachment.get("plaintext") or "").strip():
                    raise ValueError("text_attachment_plaintext_required")
                if set(self.text_attachment) - {"plaintext", "link_attachment_url"}:
                    raise ValueError("unsupported_text_attachment_field")
        if self.operation == "reply" and not self.reply_to_id:
            raise ValueError("reply_target_required")
        if self.return_to:
            value = self.return_to.strip()
            if not value.startswith("/") or value.startswith("//"):
                raise ValueError("unsafe_oauth_return_route")
        return self


@dataclass
class SocialReceipt:
    """Bounded, secret-free result. Provider credentials are never serialized here."""

    product_id: str
    platform: str
    operation: str
    ok: bool
    started_at: str
    completed_at: str
    capability: str
    account_binding_id: str | None = None
    target_account_id: str | None = None
    platform_object_id: str | None = None
    permalink: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    schema: str = "agentos.social-receipt/v1"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        _assert_secret_free(payload)
        return payload


def receipt_for(request: SocialRequest, *, started_at: str, ok: bool, capability: str, result: dict[str, Any] | None = None, error_code: str | None = None, platform_object_id: str | None = None, permalink: str | None = None) -> SocialReceipt:
    receipt = SocialReceipt(
        product_id=request.product_id, platform=request.platform, operation=request.operation,
        ok=ok, started_at=started_at, completed_at=utc_now(), capability=capability,
        account_binding_id=request.account_binding_id, target_account_id=request.target_account_id,
        platform_object_id=platform_object_id, permalink=permalink, result=result or {}, error_code=error_code,
    )
    receipt.to_dict()
    return receipt
