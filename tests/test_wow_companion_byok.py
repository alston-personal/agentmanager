import json
import unittest
from urllib.error import URLError

from scripts.wow_companion_byok import ProviderError, request_answer


class WowCompanionBYOKTests(unittest.TestCase):
    KEY = "dummy-test-secret-never-log"

    @staticmethod
    def _answer(request):
        data = json.loads(request.data)
        assert data["store"] is False
        assert data["max_output_tokens"] <= 480
        assert request.full_url == "https://api.openai.com/v1/responses"
        return json.dumps({"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "Check your quest journal."}
        ]}]}).encode("utf-8")

    def test_valid_result_is_data_only(self):
        result = request_answer("Where next?", "ask-1", self.KEY, transport=self._answer)
        self.assertEqual(result["action"], {"type": "ui.answer"})
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["answer"], "Check your quest journal.")

    def test_credential_not_in_payload(self):
        def capture(request):
            self.assertNotIn(self.KEY, request.data.decode("utf-8"))
            self.assertEqual(request.headers["Authorization"], "Bearer " + self.KEY)
            return self._answer(request)
        request_answer("Mage buff?", "ask-2", self.KEY, transport=capture)

    def test_invalid_request_id_fails_before_network(self):
        def cannot_run(request):
            self.fail("network should not be called")
        with self.assertRaises(ValueError):
            request_answer("Hi", "bad id!", self.KEY, transport=cannot_run)

    def test_bad_model_fails_before_network(self):
        with self.assertRaises(ProviderError):
            request_answer("Hi", "ask-1", self.KEY, model="model;whoami", transport=self._answer)

    def test_no_key_fails_before_network(self):
        with self.assertRaises(ProviderError):
            request_answer("Hi", "ask-1", "", transport=self._answer)

    def test_no_invented_waypoint(self):
        result = request_answer("Navigate me to a vendor", "ask-3", self.KEY, transport=self._answer)
        self.assertEqual(result["action"]["type"], "ui.answer")

    def test_provider_error_does_not_expose_key(self):
        def fail(_):
            raise URLError("secret: " + self.KEY)
        with self.assertRaises(ProviderError) as ctx:
            request_answer("Hi", "ask-1", self.KEY, transport=fail)
        self.assertNotIn(self.KEY, str(ctx.exception))

    def test_reject_empty_output(self):
        with self.assertRaises(ProviderError):
            request_answer("Hi", "ask-1", self.KEY,
                           transport=lambda req: b'{"output":[]}')

    def test_reject_excessive_response(self):
        with self.assertRaises(ProviderError):
            request_answer("Hi", "ask-1", self.KEY, transport=lambda req: b"x" * 65537)


if __name__ == "__main__":
    unittest.main()
