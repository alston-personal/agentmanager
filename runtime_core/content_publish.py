"""Governed content.publish contracts and provider resolution.

This module is intentionally transport-neutral. It validates caller-owned payloads,
resolves an already-registered provider, and builds sanitized receipts. Platform
credentials, browser profiles, and network execution stay in host/provider code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


CONTENT_ARTIFACT_SCHEMA = "agentos.content-artifact/v1"
PUBLISH_REQUEST_SCHEMA = "agentos.content-publish/v1"
PUBLISH_RECEIPT_SCHEMA = "agentos.content-publish-receipt/v1"
BATCH_RECEIPT_SCHEMA = "agentos.content-publish-batch-receipt/v1"

_ALLOWED_MODES = {"publish", "prepare"}
_FORBIDDEN_CALLER_KEYS = {
    "api_token",
    "access_token",
    "token",
    "cookie",
    "cookies",
    "shell",
    "command",
    "executable",
    "endpoint",
    "browser_script",
    "browser_javascript",
    "javascript",
    "filesystem_path",
    "file_path",
    "password",
    "secret",
    "api_secret",
    "access_secret",
}


class ProviderHealth(str, Enum):
    READY = "READY"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ResolutionStatus(str, Enum):
    READY = "READY"
    HUMAN_CONFIRM_REQUIRED = "HUMAN_CONFIRM_REQUIRED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ENTITLEMENT_REQUIRED = "ENTITLEMENT_REQUIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    DEGRADED = "DEGRADED"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProviderRecord:
    provider_id: str
    platform: str
    transport: str
    health: ProviderHealth = ProviderHealth.UNKNOWN
    auth_state: str = "UNKNOWN"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    supports_media: bool = False
    supports_reply: bool = False
    supports_thread: bool = False
    supports_unattended_publish: bool = False
    account_refs: frozenset[str] = field(default_factory=frozenset)
    priority: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ProviderRecord":
        provider_id = str(raw.get("provider_id") or "").strip()
        platform = str(raw.get("platform") or "").strip().lower()
        transport = str(raw.get("transport") or "").strip()
        if not provider_id or not platform or not transport:
            raise ValueError("provider_id, platform, and transport are required")
        health_raw = str(raw.get("health") or ProviderHealth.UNKNOWN.value).upper()
        try:
            health = ProviderHealth(health_raw)
        except ValueError as exc:
            raise ValueError(f"invalid provider health: {health_raw}") from exc
        return cls(
            provider_id=provider_id,
            platform=platform,
            transport=transport,
            health=health,
            auth_state=str(raw.get("auth_state") or "UNKNOWN"),
            capabilities=frozenset(str(x).strip() for x in raw.get("capabilities", []) if str(x).strip()),
            supports_media=bool(raw.get("supports_media", False)),
            supports_reply=bool(raw.get("supports_reply", False)),
            supports_thread=bool(raw.get("supports_thread", False)),
            supports_unattended_publish=bool(raw.get("supports_unattended_publish", False)),
            account_refs=frozenset(str(x).strip() for x in raw.get("account_refs", []) if str(x).strip()),
            priority=int(raw.get("priority", 0)),
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ProviderResolution:
    status: ResolutionStatus
    provider_id: str | None
    transport: str | None
    reason: str
    confirmation_required: bool = False


def _iter_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key).strip().lower()
            yield from _iter_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_keys(item)


def _reject_sensitive_caller_fields(value: Mapping[str, Any]) -> None:
    bad = sorted({key for key in _iter_keys(value) if key in _FORBIDDEN_CALLER_KEYS})
    if bad:
        raise ValueError("caller payload contains forbidden sensitive/executable fields: " + ", ".join(bad))


def validate_content_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    _reject_sensitive_caller_fields(artifact)
    if artifact.get("schema") != CONTENT_ARTIFACT_SCHEMA:
        raise ValueError(f"artifact schema must be {CONTENT_ARTIFACT_SCHEMA}")
    body = str(artifact.get("body") or "")
    if not body.strip():
        raise ValueError("artifact body is required")
    media = artifact.get("media", [])
    hashtags = artifact.get("hashtags", [])
    metadata = artifact.get("metadata", {})
    if not isinstance(media, list):
        raise ValueError("artifact media must be a list")
    if not isinstance(hashtags, list):
        raise ValueError("artifact hashtags must be a list")
    if not isinstance(metadata, Mapping):
        raise ValueError("artifact metadata must be an object")
    return {
        "schema": CONTENT_ARTIFACT_SCHEMA,
        "title": str(artifact.get("title") or ""),
        "body": body,
        "media": list(media),
        "link": str(artifact.get("link") or ""),
        "hashtags": [str(x) for x in hashtags],
        "reply": artifact.get("reply"),
        "metadata": dict(metadata),
    }


def validate_publish_request(request: Mapping[str, Any]) -> dict[str, Any]:
    _reject_sensitive_caller_fields(request)
    if request.get("schema") != PUBLISH_REQUEST_SCHEMA:
        raise ValueError(f"publish request schema must be {PUBLISH_REQUEST_SCHEMA}")
    required = ("project_id", "platform", "account_ref", "content_ref", "mode", "authority")
    missing = [name for name in required if not str(request.get(name) or "").strip()]
    if missing:
        raise ValueError("publish request missing required fields: " + ", ".join(missing))
    mode = str(request["mode"]).strip().lower()
    if mode not in _ALLOWED_MODES:
        raise ValueError("publish request mode must be publish or prepare")
    content_ref = str(request["content_ref"]).strip()
    if not content_ref.startswith("artifact://"):
        raise ValueError("content_ref must use artifact://")
    return {
        "schema": PUBLISH_REQUEST_SCHEMA,
        "project_id": str(request["project_id"]).strip(),
        "platform": str(request["platform"]).strip().lower(),
        "account_ref": str(request["account_ref"]).strip(),
        "content_ref": content_ref,
        "mode": mode,
        "authority": str(request["authority"]).strip(),
        "write_intent_id": str(request.get("write_intent_id") or "").strip() or None,
        "required": str(request.get("required") or "best_effort").strip().lower(),
    }


def content_hash(artifact: Mapping[str, Any]) -> str:
    normalized = validate_content_artifact(artifact)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _health_to_resolution(health: ProviderHealth) -> ResolutionStatus:
    mapping = {
        ProviderHealth.LOGIN_REQUIRED: ResolutionStatus.LOGIN_REQUIRED,
        ProviderHealth.AUTH_REQUIRED: ResolutionStatus.AUTH_REQUIRED,
        ProviderHealth.ENTITLEMENT_REQUIRED: ResolutionStatus.ENTITLEMENT_REQUIRED,
        ProviderHealth.PERMISSION_DENIED: ResolutionStatus.PERMISSION_DENIED,
        ProviderHealth.RATE_LIMITED: ResolutionStatus.RATE_LIMITED,
        ProviderHealth.DEGRADED: ResolutionStatus.DEGRADED,
        ProviderHealth.UNKNOWN: ResolutionStatus.UNKNOWN,
    }
    return mapping.get(health, ResolutionStatus.CAPABILITY_UNAVAILABLE)


class ProviderRegistry:
    def __init__(self, providers: Sequence[ProviderRecord] = ()) -> None:
        self._providers = tuple(providers)

    @classmethod
    def from_mappings(cls, values: Iterable[Mapping[str, Any]]) -> "ProviderRegistry":
        return cls(tuple(ProviderRecord.from_mapping(item) for item in values))

    def providers_for(self, platform: str, account_ref: str) -> tuple[ProviderRecord, ...]:
        platform = platform.strip().lower()
        account_ref = account_ref.strip()
        matches = [
            item
            for item in self._providers
            if item.platform == platform
            and (not item.account_refs or account_ref in item.account_refs)
        ]
        return tuple(sorted(matches, key=lambda x: (-x.priority, x.provider_id)))

    def resolve(
        self,
        request: Mapping[str, Any],
        *,
        artifact: Mapping[str, Any] | None = None,
    ) -> ProviderResolution:
        req = validate_publish_request(request)
        art = validate_content_artifact(artifact) if artifact is not None else None
        matches = list(self.providers_for(req["platform"], req["account_ref"]))
        if not matches:
            return ProviderResolution(
                ResolutionStatus.CAPABILITY_UNAVAILABLE,
                None,
                None,
                "no provider registered for platform/account",
            )

        needs_media = bool(art and art["media"])
        needs_reply = bool(art and art["reply"])
        eligible = [
            p for p in matches
            if (not needs_media or p.supports_media)
            and (not needs_reply or p.supports_reply)
        ]
        if not eligible:
            return ProviderResolution(
                ResolutionStatus.CAPABILITY_UNAVAILABLE,
                None,
                None,
                "registered providers do not satisfy required content features",
            )

        ready = [p for p in eligible if p.health is ProviderHealth.READY]
        if ready:
            unattended = [p for p in ready if p.supports_unattended_publish]
            if req["mode"] == "publish" and unattended:
                chosen = unattended[0]
                return ProviderResolution(
                    ResolutionStatus.READY,
                    chosen.provider_id,
                    chosen.transport,
                    "ready unattended provider selected",
                )
            chosen = ready[0]
            confirmation = not chosen.supports_unattended_publish or bool(chosen.metadata.get("confirmation_required"))
            return ProviderResolution(
                ResolutionStatus.HUMAN_CONFIRM_REQUIRED if confirmation else ResolutionStatus.READY,
                chosen.provider_id,
                chosen.transport,
                "ready governed assist provider selected" if confirmation else "ready provider selected",
                confirmation_required=confirmation,
            )

        best = eligible[0]
        return ProviderResolution(
            _health_to_resolution(best.health),
            best.provider_id,
            best.transport,
            f"best registered provider is {best.health.value}",
        )


def sanitize_receipt_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_CALLER_KEYS:
                continue
            clean[str(key)] = sanitize_receipt_value(item)
        return clean
    if isinstance(value, list):
        return [sanitize_receipt_value(item) for item in value]
    return value


def build_publish_receipt(
    *,
    platform: str,
    provider: str,
    account_ref: str,
    status: str,
    write_intent_id: str | None = None,
    artifact: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    confirmation_required: bool = False,
) -> dict[str, Any]:
    receipt = {
        "schema": PUBLISH_RECEIPT_SCHEMA,
        "platform": platform,
        "provider": provider,
        "account_ref": account_ref,
        "status": status,
        "write_intent_id": write_intent_id,
        "content_hash": content_hash(artifact) if artifact is not None else None,
        "confirmation_required": bool(confirmation_required),
        "credential_exposed": False,
        "result": sanitize_receipt_value(dict(result or {})),
    }
    return receipt
