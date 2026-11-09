"""Bounded, transport-neutral WoW read-only status reply.

No game transport, node identity, or runtime authority is conferred by this codec.
"""
from __future__ import annotations

import json
from typing import Any

from agentos_node.wow_control_adapter import _safe_snapshot

REPLY_SCHEMA = "agentos.wow.status.reply/v1"
MAX_REPLY_BYTES = 384


def encode_status_reply(gateway_result: dict[str, Any]) -> bytes:
    """Encode only an authenticated gateway's safe result, without raw errors."""
    if not isinstance(gateway_result, dict):
        raise ValueError("invalid_reply")
    if set(gateway_result) != {"status", "request_id", "snapshot"}:
        raise ValueError("invalid_reply_shape")
    if gateway_result["status"] != "OK":
        raise ValueError("unverified_status_reply")
    request_id = gateway_result["request_id"]
    if type(request_id) is not int or not 1 <= request_id <= 65535:
        raise ValueError("invalid_reply_id")
    snapshot = _safe_snapshot(gateway_result["snapshot"])
    wire = {"schema": REPLY_SCHEMA, "request_id": request_id, "status": "OK", "snapshot": snapshot}
    payload = json.dumps(wire, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    if len(payload) > MAX_REPLY_BYTES:
        raise ValueError("reply_too_large")
    return payload


def decode_status_reply(payload: bytes, *, expected_request_id: int) -> dict[str, Any]:
    """Validate an already trusted reply and correlation ID.

    This codec does NOT authenticate the transport; callers must do that first.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_REPLY_BYTES:
        raise ValueError("invalid_reply_bytes")
    try:
        wire = json.loads(payload.decode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid_reply_json") from exc
    if not isinstance(wire, dict) or set(wire) != {"schema", "request_id", "status", "snapshot"}:
        raise ValueError("invalid_reply_shape")
    if wire["schema"] != REPLY_SCHEMA or wire["status"] != "OK":
        raise ValueError("invalid_reply_schema")
    request_id = wire["request_id"]
    if type(request_id) is not int or request_id != expected_request_id or not 1 <= request_id <= 65535:
        raise ValueError("mismatched_reply_id")
    return {"request_id": request_id, "snapshot": _safe_snapshot(wire["snapshot"])}
