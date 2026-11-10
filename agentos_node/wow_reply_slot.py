"""Generate strictly data-only WoW Lua reply-slot content.

This module does not install files, start a Bridge or authenticate a request.
The calling trusted Windows Node transport owns atomic publishing and path safety.
"""
from __future__ import annotations

from agentos_node.wow_status_reply import decode_status_reply

SLOT_NAME = "AgentOSWoW_R001"
MAX_SLOT_LUA_BYTES = 512


def render_reply_slot(encoded_reply: bytes, *, expected_request_id: int) -> bytes:
    envelope = decode_status_reply(encoded_reply, expected_request_id=expected_request_id)
    snapshot = envelope["snapshot"]
    lines = [
        "-- Generated AgentOS read-only response data. No commands or secrets.",
        "AgentOSWoWReplySlot = {",
        "  schema = \"agentos.wow.status.reply/v1\",",
        f"  request_id = {envelope['request_id']},",
    ]
    for key in ("state", "paw", "receipt"):
        if key not in snapshot:
            continue
        value = snapshot[key]
        if value is None:
            lines.append(f"  {key} = false,")
        else:
            # Values have already passed _safe_snapshot's restrictive ASCII grammar.
            lines.append(f'  {key} = "{value}",')
    lines.append("}")
    output = ("\n".join(lines) + "\n").encode("ascii")
    if len(output) > MAX_SLOT_LUA_BYTES:
        raise ValueError("slot_too_large")
    return output
