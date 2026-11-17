"""Data-only response contract for untrusted WoW AI outputs.

Only validates candidate content; a trusted Bridge must independently authenticate,
correlate, and deliver it. No game actions, network or secret handling here.
"""
import json
import math
import re
from urllib.parse import urlsplit

SCHEMA = "agentos.wow.companion.reply/v1"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_ACTIONS = {"ui.answer", "map.waypoint"}
_CATEGORIES = {"quest", "npc", "location", "general"}


class ReplyValidationError(ValueError):
    pass


def _text(value, name, size):
    if not isinstance(value, str) or not 1 <= len(value) <= size:
        raise ReplyValidationError(f"{name}: invalid text")
    if "|" in value or any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        raise ReplyValidationError(f"{name}: markup or controls forbidden")
    return value


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ReplyValidationError("invalid request id")
    return value


def _coordinate(value):
    if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ReplyValidationError("invalid normalized coordinate")
    return float(value)


def validate_reply(value, expected_request_id):
    """Fail-closed shape validation. Does not establish factual correctness."""
    if not isinstance(value, dict) or set(value) != {
        "schema", "request_id", "category", "answer", "sources", "action"
    }:
        raise ReplyValidationError("invalid reply fields")
    if value["schema"] != SCHEMA or _id(value["request_id"]) != _id(expected_request_id):
        raise ReplyValidationError("schema or request correlation mismatch")
    if value["category"] not in _CATEGORIES:
        raise ReplyValidationError("invalid category")
    answer = _text(value["answer"], "answer", 1200)
    sources = value["sources"]
    if not isinstance(sources, list) or len(sources) > 3:
        raise ReplyValidationError("invalid sources")
    clean_sources = []
    for source in sources:
        if not isinstance(source, dict) or set(source) != {"title", "url"}:
            raise ReplyValidationError("invalid source fields")
        title = _text(source["title"], "source title", 100)
        url = _text(source["url"], "source url", 400)
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            raise ReplyValidationError("source must be HTTPS without credentials")
        clean_sources.append({"title": title, "url": url})
    action = value["action"]
    if not isinstance(action, dict) or action.get("type") not in _ACTIONS:
        raise ReplyValidationError("unsupported action")
    if action["type"] == "ui.answer":
        if set(action) != {"type"}:
            raise ReplyValidationError("unexpected UI action arguments")
        clean_action = {"type": "ui.answer"}
    else:
        if set(action) != {"type", "map_id", "x", "y", "label"}:
            raise ReplyValidationError("unexpected waypoint arguments")
        if type(action["map_id"]) is not int or not 1 <= action["map_id"] <= 1000000:
            raise ReplyValidationError("invalid map ID")
        if not clean_sources:
            raise ReplyValidationError("waypoint requires a source")
        clean_action = {
            "type": "map.waypoint", "map_id": action["map_id"],
            "x": _coordinate(action["x"]), "y": _coordinate(action["y"]),
            "label": _text(action["label"], "waypoint label", 64)
        }
    canonical = {
        "schema": SCHEMA, "request_id": value["request_id"],
        "category": value["category"], "answer": answer,
        "sources": clean_sources, "action": clean_action
    }
    if len(json.dumps(canonical, ensure_ascii=False).encode("utf-8")) > 4096:
        raise ReplyValidationError("reply too large")
    return canonical
