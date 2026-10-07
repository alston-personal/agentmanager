from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.gpt_web_response_bridge import _validate_request, atomic_json


class GptWebResponseBridgeTests(unittest.TestCase):
    def request(self):
        return {
            "schema": "agentos.session-request/v0.1",
            "request_id": "session-1",
            "provider": "gpt-web",
            "operation": "harvest",
            "session_id": "chatgpt-web:1",
            "payload": {
                "schema": "agentos.gpt-web-response-harvest/v0.1",
                "selector": "assistant.response_by_request_id",
                "request_id": "invoice:req:12345678",
                "max_characters": 65536,
            },
        }

    def test_accepts_only_scoped_harvest(self):
        self.assertEqual(
            _validate_request(self.request()),
            ("chatgpt-web:1", "invoice:req:12345678"),
        )

    def test_rejects_arbitrary_selector(self):
        payload = self.request()
        payload["payload"]["selector"] = "body.innerText"
        with self.assertRaises(ValueError):
            _validate_request(payload)

    def test_atomic_json_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "x.json"
            atomic_json(target, {"ok": True})
            self.assertIn('"ok": true', target.read_text())


if __name__ == "__main__":
    unittest.main()
