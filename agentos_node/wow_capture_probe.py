"""Decode single passive WoW capture; does not query ONE or invoke executors."""
from __future__ import annotations
import json
import sys
from agentos_node.wow_bridge_protocol import decode_request, ProtocolError

def main() -> int:
    try:
        raw = sys.stdin.read(4096)
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) != 200:
            raise ProtocolError("expected_200_pixel_cells")
        request_id, session = decode_request(payload)
    except (ProtocolError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)[:80]}))
        return 2
    # The packet is not proof of the caller's process, realm, or entitlement.
    print(json.dumps({
        "status": "DECODED_UNAUTHORIZED",
        "action": "wow.control.status",
        "request_id": request_id,
        "session_prefix": session[:4],
        "one_status": "UNKNOWN",
        "receipt_id": None,
    }))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
