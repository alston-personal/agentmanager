"""Bounded WoW AI question ingress, compatible with a future trusted local Bridge.

An AddOn packet is untrusted UI input, never authorization. This module accepts
already-decoded data from a trusted host transport. It does not capture pixels,
run a server, read game files or publish Lua. Existing WoW transport remains
owned by the #2135 migration.
"""
from __future__ import annotations

import re
from scripts.wow_companion_byok import request_answer

_SESSION = re.compile(r"^[A-Za-z0-9]{16,64}$")
_QUESTION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class CompanionIngressError(ValueError):
    pass


def validate_question(message: object) -> dict:
    if not isinstance(message, dict) or set(message) != {"action", "session", "request_id", "question"}:
        raise CompanionIngressError("INVALID_REQUEST_SHAPE")
    if message.get("action") != "ai.ask":
        raise CompanionIngressError("ACTION_NOT_ALLOWED")
    session, request_id, question = message["session"], message["request_id"], message["question"]
    if not isinstance(session, str) or not _SESSION.fullmatch(session):
        raise CompanionIngressError("INVALID_SESSION")
    if not isinstance(request_id, str) or not _QUESTION_ID.fullmatch(request_id):
        raise CompanionIngressError("INVALID_REQUEST_ID")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 500:
        raise CompanionIngressError("INVALID_QUESTION")
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in question) or "|" in question:
        raise CompanionIngressError("INVALID_QUESTION")
    return {"action": "ai.ask", "session": session, "request_id": request_id, "question": question.strip()}


class CompanionQuestionGateway:
    """Explicit local-operator opt-in; no AgentOS login required for BYOK.

    The local session verifier and credential getter are *trusted* host-side
    callbacks, never supplied by the AddOn packet. Replay history fails closed.
    """
    def __init__(self, session_verifier, credential_getter, *, provider=None, max_requests=128):
        if not callable(session_verifier) or not callable(credential_getter):
            raise TypeError("TRUSTED_HOST_CALLBACKS_REQUIRED")
        if not isinstance(max_requests, int) or type(max_requests) is not int or not 1 <= max_requests <= 1024:
            raise ValueError("INVALID_REPLAY_CAPACITY")
        self._verify = session_verifier
        self._credential = credential_getter
        self._provider = provider if provider is not None else request_answer
        if not callable(self._provider):
            raise TypeError("PROVIDER_CALLBACK_REQUIRED")
        self._seen = set()
        self._max_requests = max_requests

    def handle(self, raw: object) -> dict:
        request = validate_question(raw)
        key = (request["session"], request["request_id"])
        if key in self._seen:
            return {"status": "UNAVAILABLE", "reason": "DUPLICATE_REQUEST"}
        if len(self._seen) >= self._max_requests:
            return {"status": "UNAVAILABLE", "reason": "REPLAY_CAPACITY_EXHAUSTED"}
        # Reserve before attempting billable provider requests to avoid retries
        # that accidentally duplicate external charges after partial failure.
        self._seen.add(key)
        try:
            if self._verify(request["session"]) is not True:
                return {"status": "UNAVAILABLE", "reason": "LOCAL_SESSION_NOT_AUTHORIZED"}
            key_value = self._credential()
            if not isinstance(key_value, str) or not key_value:
                return {"status": "UNAVAILABLE", "reason": "CREDENTIAL_NOT_CONFIGURED"}
            result = self._provider(request["question"], request["request_id"], key_value)
            from scripts.wow_companion_reply import validate_reply
            validated = validate_reply(result, request["request_id"])
            # BYOK host gateway is answer-only; sourced map pins require a
            # separate verified game-knowledge path and distinct authorization.
            if validated["action"] != {"type": "ui.answer"}:
                return {"status": "UNAVAILABLE", "reason": "UNSUPPORTED_PROVIDER_ACTION"}
            return {"status": "OK", "reply": validated}
        except Exception:
            # Do not leak API keys, model errors, question text or host paths.
            return {"status": "UNAVAILABLE", "reason": "PROVIDER_UNAVAILABLE"}
