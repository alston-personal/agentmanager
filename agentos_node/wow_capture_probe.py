"""Decode a single passive WoW RGB capture, without conferring authority.

This module is the Windows capture entrypoint, not the authenticated Bridge.
Account intents are recognized here but cannot initiate OAuth/logout until a
separately authorized host Bridge binds a real account-session handler.
"""
from __future__ import annotations

import json
import sys

from agentos_node.wow_bridge_protocol import (
    ProtocolError,
    decode,
    decode_account_intent,
    decode_request,
)


def inspect_capture(cells: object) -> dict:
    if not isinstance(cells, list) or len(cells) != 200:
        raise ProtocolError("expected_200_pixel_cells")
    _, raw = decode(cells)
    try:
        message = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError("invalid_json") from exc
    if not isinstance(message, dict) or set(message) != {"action", "session"}:
        raise ProtocolError("invalid_request_shape")
    action = message.get("action")
    if action == "wow.control.status":
        request_id, session = decode_request(cells)
    elif action in {"wow.account.login.start", "wow.account.logout"}:
        request_id, session, _ = decode_account_intent(cells)
    else:
        raise ProtocolError("action_not_allowed")
    # Game supplied 'session' is a replay correlation only, NOT user identity.
    return {
        "status": "DECODED_UNAUTHORIZED",
        "action": action,
        "request_id": request_id,
        "session_prefix": session[:4],
        "one_status": "UNKNOWN",
        "receipt_id": None,
    }


def main() -> int:
    try:
        raw = sys.stdin.read(4096)
        payload = json.loads(raw)
        result = inspect_capture(payload)
    except (ProtocolError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)[:80]}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
