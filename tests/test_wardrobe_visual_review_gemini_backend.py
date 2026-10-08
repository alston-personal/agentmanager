import unittest

from capabilities.wardrobe_visual_review.gemini_backend import _classify_failure, _extract_json


class WardrobeGeminiBackendTests(unittest.TestCase):
    def test_extracts_plain_json(self):
        payload = _extract_json('{"schema":"agentos.wardrobe-visual-semantic-receipt/v1","backendReady":true,"checks":[]}')
        self.assertEqual(payload["schema"], "agentos.wardrobe-visual-semantic-receipt/v1")
        self.assertTrue(payload["backendReady"])

    def test_extracts_fenced_json(self):
        payload = _extract_json('note\n\x60\x60\x60json\n{"backendReady":true,"checks":[]}\n\x60\x60\x60')
        self.assertTrue(payload["backendReady"])

    def test_classifies_auth_and_rate_limit(self):
        self.assertEqual(_classify_failure("Please sign in"), "AUTH_REQUIRED")
        self.assertEqual(
            _classify_failure("IneligibleTierError: This client is no longer supported. Migrate to Antigravity"),
            "OAUTH_CLIENT_UNSUPPORTED",
        )
        self.assertEqual(_classify_failure("Resource exhausted: quota"), "RATE_LIMITED")
        self.assertEqual(_classify_failure("", timed_out=True), "TIMEOUT")


if __name__ == "__main__":
    unittest.main()
