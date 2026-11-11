"""Strict public account/Realm projection for a game-visible one-shot reply.

A game reply carries *display data*, never an OAuth token, pairing verifier,
host session handle or authorization. The trusted Bridge must first authenticate
the host session and query ONE for the user's Realm permissions.
"""
from __future__ import annotations

import json
import re
from typing import Any

SCHEMA = "agentos.wow.account.reply/v1"
ACCOUNT = re.compile(r"^[A-Za-z0-9@._+-]{1,128}$")
REALM = re.compile(r"^(?:realm-u-[0-9a-f]{24}|realm-[a-z0-9][a-z0-9-]{0,63})$")
STATES = {"PAIRING_STARTED", "SIGNED_IN", "SIGNED_OUT", "REVOCATION_UNCONFIRMED", "REALM_SELECTED"}
MAX_BYTES = 384


def _validate(snapshot: Any) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or set(snapshot) != {"status", "signed_in", "account", "realm"}:
        raise ValueError("invalid_account_projection")
    if snapshot["status"] not in STATES or type(snapshot["signed_in"]) is not bool:
        raise ValueError("invalid_account_state")
    account, realm = snapshot["account"], snapshot["realm"]
    if snapshot["signed_in"]:
        if snapshot["status"] not in {"SIGNED_IN", "REALM_SELECTED"}:
            raise ValueError("invalid_signed_in_status")
        if not isinstance(account, str) or not ACCOUNT.fullmatch(account):
            raise ValueError("invalid_account_label")
        if realm is not None and (not isinstance(realm, str) or not REALM.fullmatch(realm)):
            raise ValueError("invalid_realm_label")
    elif account is not None or realm is not None:
        raise ValueError("unauthorized_identity_leak")
    return dict(snapshot)


def encode_account_reply(request_id: int, projection: dict[str, Any]) -> bytes:
    if type(request_id) is not int or not 1 <= request_id <= 65535:
        raise ValueError("invalid_account_reply_id")
    public = _validate(projection)
    wire = {"schema": SCHEMA, "request_id": request_id, "projection": public}
    data = json.dumps(wire, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if len(data) > MAX_BYTES:
        raise ValueError("oversized_account_reply")
    return data


def decode_account_reply(data: bytes, *, expected_request_id: int) -> dict[str, Any]:
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ValueError("invalid_reply_bytes")
    try:
        wire = json.loads(data.decode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid_reply_json") from exc
    if not isinstance(wire, dict) or set(wire) != {"schema", "request_id", "projection"}:
        raise ValueError("invalid_reply_shape")
    if wire["schema"] != SCHEMA or type(wire["request_id"]) is not int or wire["request_id"] != expected_request_id:
        raise ValueError("unmatched_account_reply")
    return _validate(wire["projection"])
