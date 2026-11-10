"""Portable media validation for content.publish delivery.

This module does not upload, copy, or expose local files. It only validates an
already-produced AgentOS media asset envelope and selects an approved public
HTTPS delivery location for social publishing.
"""
from __future__ import annotations

import re
from typing import Any, Mapping
from urllib.parse import urlsplit


MEDIA_ASSET_SCHEMA = "agentos.media.asset.v0"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def resolve_public_media_asset(asset_ref: str, envelope: Mapping[str, Any]) -> dict[str, str]:
    ref = str(asset_ref or "").strip()
    if not ref.startswith("asset://"):
        raise ValueError("content_publish_media_asset_ref_required")
    if envelope.get("schema") != MEDIA_ASSET_SCHEMA:
        raise ValueError("content_publish_media_asset_schema_invalid")

    asset_id = str(envelope.get("asset_id") or "").strip()
    owner_scope = str(envelope.get("owner_scope") or "").strip()
    if not asset_id.startswith("asset:") or not owner_scope:
        raise ValueError("content_publish_media_asset_identity_invalid")

    content = envelope.get("content")
    if not isinstance(content, Mapping):
        raise ValueError("content_publish_media_asset_content_invalid")
    mime = str(content.get("mime") or "").strip().lower()
    sha256 = str(content.get("sha256") or "").strip().lower()
    if not mime.startswith("image/") or not _SHA256_RE.fullmatch(sha256):
        raise ValueError("content_publish_media_asset_integrity_invalid")

    rights = envelope.get("rights")
    if not isinstance(rights, Mapping) or rights.get("publication_allowed") is not True:
        raise PermissionError("content_publish_media_publication_not_allowed")

    integrity = envelope.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("human_approved") is not True:
        raise PermissionError("content_publish_media_not_human_approved")

    if str(envelope.get("state") or "") != "approved":
        raise PermissionError("content_publish_media_state_not_approved")

    locations = envelope.get("locations")
    if not isinstance(locations, list):
        raise ValueError("content_publish_media_locations_invalid")

    candidates: list[str] = []
    for item in locations:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("kind") or "") != "public_https":
            continue
        if item.get("expires_at") not in (None, ""):
            # Expiring delivery requires an explicit refresh contract. Do not
            # silently approve a URL whose lifetime cannot be proven here.
            continue
        uri = str(item.get("uri") or "").strip()
        parsed = urlsplit(uri)
        if (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and len(uri) <= 2048
        ):
            candidates.append(uri)

    if len(candidates) != 1:
        raise ValueError("content_publish_media_public_https_delivery_required")

    return {
        "asset_ref": ref,
        "asset_id": asset_id,
        "owner_scope": owner_scope,
        "mime": mime,
        "sha256": sha256,
        "public_url": candidates[0],
    }
