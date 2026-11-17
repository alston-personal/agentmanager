"""Render validated AI display data for the existing WoW one-shot reply-slot concept.

Pure transformation only: no game-file writes, token storage, or add-on loading.
The trusted host publisher must enforce pre-existing slot paths, per-request
correlation, atomic replacement and game-client compatibility separately.
"""
from scripts.wow_companion_reply import validate_reply

SLOT_SCHEMA = "agentos.wow.companion.reply/v1"
MAX_SLOT_BYTES = 16384


class CompanionSlotError(ValueError):
    pass


def _lua_bytes(value: str) -> str:
    # Decimal escapes are byte-oriented and cannot terminate a Lua string.
    # Unicode UTF-8 survives as bytes, without Lua source injection.
    raw = value.encode("utf-8")
    return '"' + "".join("\\%03d" % byte for byte in raw) + '"'


def render_companion_slot(reply: dict, expected_request_id: str) -> bytes:
    normalized = validate_reply(reply, expected_request_id)
    action = normalized["action"]
    if action["type"] != "ui.answer":
        raise CompanionSlotError("WAYPOINT_REQUIRES_VERIFIED_NAV_ADAPTER")
    # Keep the legacy AgentOSWoWReplySlot variable used by #2135;
    # the game UI must explicitly recognize this distinct schema.
    lines = [
        "-- Companion data-only reply. NOT an instruction or authorization.",
        "AgentOSWoWReplySlot = {",
        "  schema = " + _lua_bytes(SLOT_SCHEMA) + ",",
        "  request_id = " + _lua_bytes(normalized["request_id"]) + ",",
        "  answer = " + _lua_bytes(normalized["answer"]) + ",",
        "  category = " + _lua_bytes(normalized["category"]) + ",",
        "  action = " + _lua_bytes("ui.answer") + ",",
        "}",
        "",
    ]
    output = "\n".join(lines).encode("ascii")
    if len(output) > MAX_SLOT_BYTES:
        raise CompanionSlotError("SLOT_TOO_LARGE")
    return output
