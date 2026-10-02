"""Projection from governed content.publish into Shared Social Runtime.

This module is pure: it does not read host credentials, issue write acceptance,
or perform network/publication side effects.
"""
from __future__ import annotations

from typing import Any, Mapping

from agentos_node.social.contracts import SocialRequest
from runtime_core.content_publish import (
    content_hash,
    validate_content_artifact,
    validate_publish_request,
)
from runtime_core.content_publish_media import resolve_public_media_asset


def _threads_text(artifact: Mapping[str, Any]) -> str:
    normalized = validate_content_artifact(artifact)
    metadata = normalized.get("metadata") or {}
    platform_copy = metadata.get("platform_copy") if isinstance(metadata, Mapping) else None
    if isinstance(platform_copy, Mapping):
        specific = str(platform_copy.get("threads") or "").strip()
        if specific:
            return specific
    return str(normalized["body"]).strip()


def _threads_media(
    artifact: Mapping[str, Any],
    *,
    media_resolutions: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[str] | None, list[str] | None, list[dict[str, str]]]:
    normalized = validate_content_artifact(artifact)
    media = normalized.get("media") or []
    if not media:
        return None, None, []

    resolutions = dict(media_resolutions or {})
    urls: list[str] = []
    alts: list[str] = []
    evidence: list[dict[str, str]] = []
    for index, item in enumerate(media):
        if isinstance(item, str):
            ref = item
            alt = ""
        else:
            ref = str(item.get("ref") or "")
            alt = str(item.get("alt") or item.get("alt_text") or "")

        if ref.startswith("asset://"):
            envelope = resolutions.get(ref)
            if not isinstance(envelope, Mapping):
                raise ValueError("content_publish_media_resolution_required")
            resolved = resolve_public_media_asset(ref, envelope)
            url = resolved["public_url"]
            evidence.append(resolved)
        else:
            if not ref.startswith("https://"):
                raise ValueError("content_publish_threads_media_https_required")
            url = ref

        if not alt.strip():
            alt = f"content image {index + 1}"
        urls.append(url)
        alts.append(alt[:1000])

    if len(urls) > 20:
        raise ValueError("content_publish_threads_media_limit_exceeded")
    return urls, alts, evidence


def build_threads_social_request(
    publish_request: Mapping[str, Any],
    artifact: Mapping[str, Any],
    account: Mapping[str, Any],
    *,
    media_resolutions: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project an exact approved content.publish request into SocialRequest.

    Authority text is evidence/intent, not authorization. This function never
    issues a runtime acceptance. The caller must separately supply one exact
    one-shot acceptance at execution time.
    """
    request = validate_publish_request(publish_request)
    normalized = validate_content_artifact(artifact)

    if request["mode"] != "publish":
        raise ValueError("content_publish_social_execution_requires_publish_mode")
    if request["platform"] != "threads":
        raise ValueError("content_publish_social_execution_requires_threads")
    if request["authority"] != "approved-content-publish":
        raise ValueError("content_publish_social_execution_authority_not_approved")
    if str(account.get("account_ref") or "") != request["account_ref"]:
        raise ValueError("content_publish_social_account_ref_mismatch")
    if str(account.get("product_id") or "") != "content-publish":
        raise ValueError("content_publish_social_product_scope_mismatch")
    if str(account.get("platform") or "") != "threads":
        raise ValueError("content_publish_social_platform_scope_mismatch")

    binding_id = str(account.get("binding_id") or "").strip()
    provider_account_id = str(account.get("provider_account_id") or "").strip()
    if not binding_id or not provider_account_id:
        raise ValueError("content_publish_social_binding_not_ready")

    urls, alts, media_evidence = _threads_media(
        normalized,
        media_resolutions=media_resolutions,
    )
    kwargs: dict[str, Any] = {
        "product_id": "content-publish",
        "platform": "threads",
        "operation": "publish",
        "account_binding_id": binding_id,
        "target_account_id": provider_account_id,
        "primary_text": _threads_text(normalized),
        "write_intent_id": request["write_intent_id"],
        "schema": "agentos.social-request/v1",
    }
    if urls:
        if len(urls) == 1:
            kwargs["image_url"] = urls[0]
            kwargs["image_alt_text"] = alts[0]
        else:
            kwargs["image_urls"] = urls
            kwargs["image_alt_texts"] = alts

    social = SocialRequest(**kwargs).validate()
    payload = {
        key: value
        for key, value in social.__dict__.items()
        if value is not None
    }
    payload["content_hash"] = content_hash(normalized)
    payload["media_resolution"] = media_evidence
    return payload


def social_request_payload(projected: Mapping[str, Any]) -> dict[str, Any]:
    """Return only fields accepted by SocialRequest, excluding projection metadata."""
    allowed = set(SocialRequest.__dataclass_fields__)
    return {key: value for key, value in projected.items() if key in allowed}
