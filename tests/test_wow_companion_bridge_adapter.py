import unittest

from scripts.wow_companion_bridge_adapter import QuestionBridgeAdapter
from scripts.wow_companion_frames import encode_question
from scripts.wow_companion_reply import SCHEMA


class QuestionBridgeAdapterTests(unittest.TestCase):
    SESSION = b"abcdefgh"

    def _captures(self, question, qid=72):
        return [frame + [0] * (200 - len(frame))
                for frame in encode_question(self.SESSION, qid, question)]

    def _provider(self, question, request_id, key):
        self.assertEqual(key, "in-memory-test-key")
        return {"schema": SCHEMA, "request_id": request_id, "category": "general",
                "answer": "Ask a city guard.", "sources": [],
                "action": {"type": "ui.answer"}}

    def _adapter(self, verifier=None, provider=None):
        return QuestionBridgeAdapter(
            verifier if verifier is not None else (lambda s: s == self.SESSION.hex()),
            lambda: "in-memory-test-key", provider=provider or self._provider
        )

    def test_padded_capture_to_unpublished_data_slot(self):
        adapter = self._adapter()
        captures = self._captures("Mage trainer?")
        for captured in captures:
            result = adapter.accept_capture(captured)
        self.assertEqual(result["status"], "SLOT_READY")
        self.assertFalse(result["published"])
        self.assertFalse(result["game_received"])
        self.assertEqual(result["request_id"], "ask-72")
        self.assertIn(b"AgentOSWoWReplySlot", result["slot_bytes"])
        self.assertNotIn(b"in-memory-test-key", result["slot_bytes"])

    def test_multiframe_requires_all_parts(self):
        adapter = self._adapter()
        frames = self._captures("法師要如何加秘法智慧？" * 15)
        for frame in frames[:-1]:
            result = adapter.accept_capture(frame)
            self.assertEqual(result["status"], "PART_CAPTURED")
            self.assertNotIn("slot_bytes", result)
        result = adapter.accept_capture(frames[-1])
        self.assertEqual(result["status"], "SLOT_READY")

    def test_untrusted_session_cannot_call_provider(self):
        calls = []
        def provider(*_):
            calls.append(1)
            return {}
        adapter = self._adapter(verifier=lambda _: False, provider=provider)
        result = adapter.accept_capture(self._captures("hello")[0])
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["reason"], "LOCAL_SESSION_NOT_AUTHORIZED")
        self.assertEqual(calls, [])

    def test_duplicate_query_cannot_be_billed_twice(self):
        calls = []
        def provider(q, request_id, key):
            calls.append(1)
            return self._provider(q, request_id, key)
        adapter = self._adapter(provider=provider)
        frame = self._captures("hello")[0]
        self.assertEqual(adapter.accept_capture(frame)["status"], "SLOT_READY")
        self.assertEqual(adapter.accept_capture(frame)["reason"], "DUPLICATE_REQUEST")
        self.assertEqual(len(calls), 1)

    def test_corrupted_capture_never_reaches_provider(self):
        calls = []
        def provider(*_):
            calls.append(1)
        adapter = self._adapter(provider=provider)
        frame = self._captures("hello")[0]
        bad = frame[:]
        bad[100] = 1
        self.assertEqual(adapter.accept_capture(bad)["status"], "REJECTED")
        self.assertEqual(calls, [])

    def test_provider_error_does_not_leak(self):
        def provider(*_):
            raise RuntimeError("super-secret-key")
        adapter = self._adapter(provider=provider)
        result = adapter.accept_capture(self._captures("hello")[0])
        self.assertEqual(result, {"status": "UNAVAILABLE", "reason": "PROVIDER_UNAVAILABLE"})


if __name__ == "__main__":
    unittest.main()
