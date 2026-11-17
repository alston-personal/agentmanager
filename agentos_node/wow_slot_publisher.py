"""Publish one validated WoW status reply to a pre-existing one-shot addon slot.

This is an opt-in host-side helper, not a daemon, installer, authentication
mechanism or gameplay automation. The trusted caller owns Node/ONE verification.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from typing import Any

SLOT_NAME = "AgentOSWoW_R001"


class SlotPublishError(RuntimeError):
    """Sanitized failure. Never contains host paths or credentials."""


def _existing_slot_file(slot_dir: Path) -> Path:
    """Accept only an already installed, non-symlinked exact slot."""
    if not isinstance(slot_dir, Path) or slot_dir.name != SLOT_NAME:
        raise SlotPublishError("INVALID_SLOT_DIRECTORY")
    if slot_dir.is_symlink() or not slot_dir.is_dir():
        raise SlotPublishError("SLOT_NOT_INSTALLED")
    # Never create an unapproved addon or select an arbitrary filename.
    toc = slot_dir / (SLOT_NAME + ".toc")
    target = slot_dir / "Reply.lua"
    for path in (toc, target):
        if path.is_symlink():
            raise SlotPublishError("UNSAFE_SLOT_PATH")
        try:
            mode = os.lstat(path).st_mode
        except OSError as exc:
            raise SlotPublishError("SLOT_NOT_INSTALLED") from exc
        if not stat.S_ISREG(mode):
            raise SlotPublishError("UNSAFE_SLOT_PATH")
    if b"## LoadOnDemand: 1" not in toc.read_bytes()[:1024]:
        raise SlotPublishError("UNSUPPORTED_SLOT")
    return target


def publish_status_reply(cells: list[int], gateway: Any, slot_dir: Path) -> dict[str, Any]:
    """Decode and authorize via existing Node, then atomically replace slot data.

    A caller must provide a *previously trusted* host gateway and a verified
    installed addon directory. Unavailable/unsafe results never touch files.
    """
    from agentos_node.wow_bridge_protocol import decode_request
    from agentos_node.wow_reply_slot import render_reply_slot
    from agentos_node.wow_status_reply import encode_status_reply

    request_id, _session = decode_request(cells)
    result = gateway.accept(cells)
    if not isinstance(result, dict) or result.get("status") != "OK":
        return {"status": "UNAVAILABLE", "reason": "GATEWAY_REJECTED"}
    if type(result.get("request_id")) is not int or result["request_id"] != request_id:
        return {"status": "UNAVAILABLE", "reason": "CORRELATION_REJECTED"}
    # Validate and render BEFORE inspecting or modifying filesystem.
    data = render_reply_slot(encode_status_reply(result), expected_request_id=request_id)
    target = _existing_slot_file(slot_dir)
    _atomic_write(target, data, slot_dir)
    return {"status": "PUBLISHED", "request_id": request_id}

def _atomic_write(target: Path, data: bytes, slot_dir: Path) -> None:
    """Shared atomic publisher; all callers must validate the exact installed slot."""
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".agentos-reply-", suffix=".tmp", dir=str(slot_dir))
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError:
        raise SlotPublishError("SLOT_PUBLISH_FAILED") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def publish_companion_answer(candidate: dict, slot_dir: Path, *, expected_request_id: str) -> dict:
    """Publish a PRE-VALIDATED data-only candidate to the existing reply slot.

    Caller must supply the output of a trusted local session-bound Bridge.
    No authentication is inferred from candidate data, paths or game pixels.
    Publishing does not prove that the game has loaded the reply.
    """
    from scripts.wow_companion_reply import validate_reply
    from scripts.wow_companion_slot import render_companion_slot
    try:
        validated = validate_reply(candidate, expected_request_id)
        data = render_companion_slot(validated, expected_request_id)
    except (ValueError, TypeError):
        raise SlotPublishError("COMPANION_REPLY_REJECTED") from None
    target = _existing_slot_file(slot_dir)
    _atomic_write(target, data, slot_dir)
    return {
        "status": "PUBLISHED",
        "request_id": expected_request_id,
        "game_received": False,
    }
