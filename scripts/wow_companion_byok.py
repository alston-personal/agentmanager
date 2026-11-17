"""Direct BYOK OpenAI API provider for the WoW Companion host-side Bridge.

This module runs outside WoW. Credentials must be supplied by the host credential
store at request time, never persisted to AddOn SavedVariables or logs.
It returns a display-only candidate, not permission to invoke a game action.
"""
import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from scripts.wow_companion_reply import SCHEMA, validate_reply

API_URL = "https://api.openai.com/v1/responses"
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_MAX_RESPONSE = 65536


class ProviderError(RuntimeError):
    pass


def _extract_text(payload):
    if not isinstance(payload, dict):
        raise ProviderError("invalid provider response")
    lines = []
    for output in payload.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for item in output.get("content", []):
            if isinstance(item, dict) and item.get("type") == "output_text":
                if isinstance(item.get("text"), str):
                    lines.append(item["text"])
    text = "\n".join(lines).strip()
    if not text or len(text) > 1200:
        raise ProviderError("empty or excessive response")
    return text


def request_answer(question, request_id, api_key, *, model="gpt-5-mini", transport=None):
    """Make one bounded request; transport is injectable for offline testing.

    This provider does NOT claim web-search, game-state access or verified waypoints.
    The result is always 'ui.answer', never a gameplay action.
    """
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise ProviderError("invalid question")
    if not isinstance(api_key, str) or not 8 <= len(api_key) <= 512 or any(c.isspace() for c in api_key):
        raise ProviderError("missing or invalid API credential")
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise ProviderError("invalid model name")
    # Validate correlation before calling a chargeable API.
    skeleton = {
        "schema": SCHEMA, "request_id": request_id, "category": "general",
        "answer": "pending", "sources": [], "action": {"type": "ui.answer"}
    }
    validate_reply(skeleton, request_id)
    body = json.dumps({
        "model": model,
        "instructions": (
            "Answer World of Warcraft questions concisely. State uncertainty; "
            "do not invent NPC locations, coordinates, game state, sources or game commands. "
            "You cannot see the player's live game session or browse the web."
        ),
        "input": question.strip(),
        "max_output_tokens": 480,
        "store": False,
    }).encode("utf-8")
    req = Request(API_URL, data=body, headers={
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }, method="POST")
    sender = transport if transport is not None else _post
    try:
        provider_response = sender(req)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        # Never log exception representations: they might contain URLs or secrets.
        raise ProviderError("AI provider request failed") from None
    if not isinstance(provider_response, (bytes, bytearray)) or len(provider_response) > _MAX_RESPONSE:
        raise ProviderError("invalid provider response size")
    try:
        answer = _extract_text(json.loads(provider_response))
    except (ValueError, UnicodeError, TypeError, KeyError) as exc:
        raise ProviderError("invalid provider JSON") from None
    candidate = dict(skeleton, answer=answer)
    return validate_reply(candidate, request_id)


def _post(request):
    with urlopen(request, timeout=15) as response:
        data = response.read(_MAX_RESPONSE + 1)
    return data
