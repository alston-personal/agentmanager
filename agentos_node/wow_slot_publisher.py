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

from agentos_node.wow_reply_slot import SLOT_NAME, render_reply_slot
from agentos_node.wow_status_reply import encode_status_reply


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

    request_id, _session = decode_request(cells)
    result = gateway.accept(cells)
    if not isinstance(result, dict) or result.get("status") != "OK":
        return {"status": "UNAVAILABLE", "reason": "GATEWAY_REJECTED"}
    if type(result.get("request_id")) is not int or result["request_id"] != request_id:
        return {"status": "UNAVAILABLE", "reason": "CORRELATION_REJECTED"}
    # Validate and render BEFORE inspecting or modifying filesystem.
    data = render_reply_slot(encode_status_reply(result), expected_request_id=request_id)
    target = _existing_slot_file(slot_dir)
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".agentos-reply-", suffix=".tmp", dir=str(slot_dir))
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    except OSError as exc:
        raise SlotPublishError("SLOT_PUBLISH_FAILED") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
    return {"status": "PUBLISHED", "request_id": request_id}
