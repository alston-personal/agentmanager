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

def render_account_reply_slot(encoded_reply: bytes, *, expected_request_id: int) -> bytes:
    """Render allowlisted public account labels; no arbitrary Lua or secrets."""
    from agentos_node.wow_account_reply import decode_account_reply
    projection = decode_account_reply(encoded_reply, expected_request_id=expected_request_id)
    lines = [
        "-- Generated untrusted display data only. Not an authorization.",
        "AgentOSWoWReplySlot = {",
        '  schema = "agentos.wow.account.reply/v1",',
        f"  request_id = {expected_request_id},",
        f'  status = "{projection["status"]}",',
        f'  signed_in = {"true" if projection["signed_in"] else "false"},',
    ]
    for key in ("account", "realm"):
        value = projection[key]
        if value is not None:
            lines.append(f'  {key} = "{value}",')
    lines.append("}")
    content = ("\n".join(lines) + "\n").encode("ascii")
    if len(content) > MAX_SLOT_LUA_BYTES:
        raise ValueError("slot_too_large")
    return content
