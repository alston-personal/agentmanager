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
            "canonical_reply": result["reply"],
            "published": False,
            "game_received": False,
        }

    def accept_and_publish(self, rgb_cells, slot_dir):
        """Explicit opt-in disk publication after trusted host verification.

        Does not capture the screen or prove that the running WoW AddOn read
        the slot. No input from game pixels can select an output directory.
        """
        prepared = self.accept_capture(rgb_cells)
        if prepared.get("status") != "SLOT_READY":
            return prepared
        from agentos_node.wow_slot_publisher import (
            SlotPublishError, publish_companion_answer,
        )
        try:
            result = publish_companion_answer(
                prepared["canonical_reply"],
                slot_dir,
                expected_request_id=prepared["request_id"],
            )
        except SlotPublishError:
            return {"status": "UNAVAILABLE", "reason": "SLOT_PUBLISH_REJECTED"}
        return {
            "status": result["status"],
            "request_id": prepared["request_id"],
            "published": True,
            "game_received": False,
        }
