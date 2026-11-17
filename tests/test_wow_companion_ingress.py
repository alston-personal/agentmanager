import unittest

from scripts.wow_companion_ingress import (
    CompanionIngressError, CompanionQuestionGateway, validate_question
)
from scripts.wow_companion_reply import SCHEMA


class CompanionIngressTests(unittest.TestCase):
    SESSION = "session1234567890"
    MESSAGE = {"action": "ai.ask", "session": SESSION,
               "request_id": "ask-7", "question": "Where is the mage trainer?"}

    def _gateway(self, *, verifier=None, credentials=None, provider=None, capacity=128):
        def sample_answer(question, request_id, key):
            self.assertEqual(key, "test-key-in-memory")
            return {"schema": SCHEMA, "request_id": request_id,
                    "category": "general", "answer": "See a class trainer.",
                    "sources": [], "action": {"type": "ui.answer"}}
        return CompanionQuestionGateway(
            verifier or (lambda session: session == self.SESSION),
            credentials or (lambda: "test-key-in-memory"),
            provider=provider or sample_answer, max_requests=capacity)

    def test_valid_answer(self):
        result = self._gateway().handle(dict(self.MESSAGE))
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["reply"]["action"], {"type": "ui.answer"})

    def test_no_agentos_identity_required(self):
        self.assertEqual(self._gateway().handle(dict(self.MESSAGE))["status"], "OK")

    def test_replay_denied_and_not_billed_twice(self):
        calls = []
        def provider(question, request_id, key):
            calls.append(1)
            return {"schema": SCHEMA, "request_id": request_id,
                    "category": "general", "answer": "Yes.",
                    "sources": [], "action": {"type": "ui.answer"}}
        gateway = self._gateway(provider=provider)
        self.assertEqual(gateway.handle(dict(self.MESSAGE))["status"], "OK")
        self.assertEqual(gateway.handle(dict(self.MESSAGE))["reason"], "DUPLICATE_REQUEST")
        self.assertEqual(len(calls), 1)

    def test_session_fail_closed(self):
        gateway = self._gateway(verifier=lambda session: "yes")
        self.assertEqual(gateway.handle(dict(self.MESSAGE))["reason"], "LOCAL_SESSION_NOT_AUTHORIZED")

    def test_missing_credential(self):
        gateway = self._gateway(credentials=lambda: None)
        self.assertEqual(gateway.handle(dict(self.MESSAGE))["reason"], "CREDENTIAL_NOT_CONFIGURED")

    def test_explicit_action_allowlist(self):
        msg = dict(self.MESSAGE, action="wow.cast")
        with self.assertRaises(CompanionIngressError):
            validate_question(msg)

    def test_no_raw_token_or_shell_fields(self):
        with self.assertRaises(CompanionIngressError):
            validate_question(dict(self.MESSAGE, shell="powershell"))

    def test_markup_injection_denied(self):
        with self.assertRaises(CompanionIngressError):
            validate_question(dict(self.MESSAGE, question="|Hurl:foo|hclick|h"))

    def test_provider_exception_sanitized(self):
        def failure(*args):
            raise RuntimeError("test-key-in-memory")
        result = self._gateway(provider=failure).handle(dict(self.MESSAGE))
        self.assertEqual(result, {"status": "UNAVAILABLE", "reason": "PROVIDER_UNAVAILABLE"})

    def test_wrong_reply_id_rejected(self):
        def failure(question, request_id, key):
            return {"schema": SCHEMA, "request_id": "ask-wrong", "category": "general",
                    "answer": "wrong", "sources": [], "action": {"type": "ui.answer"}}
        self.assertEqual(self._gateway(provider=failure).handle(dict(self.MESSAGE))["reason"], "PROVIDER_UNAVAILABLE")

    def test_external_map_action_rejected(self):
        def unexpected(question, request_id, key):
            return {"schema": SCHEMA, "request_id": request_id, "category": "location",
                    "answer": "Somewhere", "sources": [{"title": "test", "url": "https://example.com"}],
                    "action": {"type": "map.waypoint", "map_id": 1, "x": .1, "y": .2, "label": "Pin"}}
        self.assertEqual(self._gateway(provider=unexpected).handle(dict(self.MESSAGE))["reason"], "UNSUPPORTED_PROVIDER_ACTION")

    def test_capacity_fail_closed(self):
        gateway = self._gateway(capacity=1)
        self.assertEqual(gateway.handle(dict(self.MESSAGE))["status"], "OK")
        msg = dict(self.MESSAGE, request_id="ask-8")
        self.assertEqual(gateway.handle(msg)["reason"], "REPLAY_CAPACITY_EXHAUSTED")

    def test_bool_capacity_invalid(self):
        with self.assertRaises(ValueError):
            self._gateway(capacity=True)


if __name__ == "__main__":
    unittest.main()
