"""Host-side adapter connecting captured WoW question frames to existing BYOK.

This is NOT a new listener or game transport. The caller must independently
authenticate the local game session, capture the actual screen and deliver any
generated data via the already-governed one-shot reply slot. No filesystem
access, Node enrollment, gameplay actions, background retries or host secrets.
"""
from scripts.wow_companion_ingress import CompanionQuestionGateway
from scripts.wow_companion_receiver import QuestionFrameReceiver
from scripts.wow_companion_slot import render_companion_slot


class QuestionBridgeAdapter:
    """Strict, single-purpose adapter for an already trusted capture caller."""

    def __init__(self, session_verifier, credential_getter, *, provider=None, clock=None):
        self._receiver = QuestionFrameReceiver(clock=clock)
        self._gateway = CompanionQuestionGateway(
            session_verifier, credential_getter, provider=provider
        )

    def accept_capture(self, rgb_cells):
        """Return only host-local capture status and a candidate bytes payload.

        'SLOT_READY' is NOT a game ACK or proof that a slot was published.
        """
        parsed = self._receiver.accept(rgb_cells)
        if parsed["status"] == "REJECTED":
            return parsed
        if parsed["status"] == "PART_CAPTURED":
            return parsed
        request = parsed["request"]
        result = self._gateway.handle(request)
        if result.get("status") != "OK":
            return {"status": "UNAVAILABLE", "reason": result.get("reason", "GATEWAY_REJECTED")}
        try:
            payload = render_companion_slot(result["reply"], request["request_id"])
        except (ValueError, TypeError):
            return {"status": "UNAVAILABLE", "reason": "SLOT_RENDER_REJECTED"}
        return {
            "status": "SLOT_READY",
            "request_id": request["request_id"],
            "slot_bytes": payload,
            "published": False,
            "game_received": False,
        }
