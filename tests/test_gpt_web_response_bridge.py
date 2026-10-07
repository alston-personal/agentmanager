from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.gpt_web_response_bridge import (
    _chatgpt_target,
    _open_target_connection,
    _responsive_chatgpt_target,
    _validate_request,
    atomic_json,
)


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
        session_id, request_id, inner = _validate_request(self.request())
        self.assertEqual((session_id, request_id), ("chatgpt-web:1", "invoice:req:12345678"))
        self.assertEqual(inner["selector"], "assistant.response_by_request_id")

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

    def test_accepts_scoped_vision_invoke(self):
        payload = self.request()
        payload["operation"] = "invoke"
        payload["payload"] = {
            "schema":"agentos.gpt-web-vision-invoke/v0.1",
            "request_id":"invoice:req:12345678",
            "capability":"vision.invoice.extract",
            "image_path":"/home/ubuntu/agentmanager/benchmarks/invoice_handwriting/fixtures/x.png",
            "prompt":"return json with invoice:req:12345678",
        }
        session_id, request_id, inner = _validate_request(payload)
        self.assertEqual(session_id, "chatgpt-web:1")
        self.assertEqual(request_id, "invoice:req:12345678")
        self.assertEqual(inner["capability"], "vision.invoice.extract")

    def test_chatgpt_target_prefers_page_with_websocket(self):
        targets = [
            {"type":"page","url":"https://example.com/","webSocketDebuggerUrl":"ws://x"},
            {"type":"page","url":"https://chatgpt.com/c/123","webSocketDebuggerUrl":"ws://chat"},
        ]
        with patch("scripts.gpt_web_response_bridge._targets", return_value=targets):
            target = _chatgpt_target("http://127.0.0.1:9222")
        self.assertEqual(target["webSocketDebuggerUrl"], "ws://chat")

    def test_missing_chatgpt_target_can_bootstrap(self):
        created = {"id":"p1","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://chat"}
        with patch("scripts.gpt_web_response_bridge._targets", return_value=[]), \
             patch("scripts.gpt_web_response_bridge._create_target", return_value=created):
            target = _chatgpt_target("http://127.0.0.1:9222", create_if_missing=True)
        self.assertEqual(target["id"], "p1")

    def test_responsive_target_rejects_unresponsive_socket(self):
        target={"id":"p1","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://dead"}
        with patch("scripts.gpt_web_response_bridge._chatgpt_target", return_value=target), \
             patch("scripts.gpt_web_response_bridge._targets", return_value=[target]), \
             patch("scripts.gpt_web_response_bridge.CdpPage", side_effect=TimeoutError("CDP_WS_CONNECT_TIMEOUT")):
            with self.assertRaisesRegex(RuntimeError, "CHATGPT_CDP_TARGET_UNRESPONSIVE"):
                _responsive_chatgpt_target("http://127.0.0.1:9222")

    def test_browser_session_fallback_when_page_socket_stalls(self):
        target={"id":"p1","type":"page","url":"https://chatgpt.com/","webSocketDebuggerUrl":"ws://page"}
        direct = Mock()
        direct.evaluate.side_effect = TimeoutError("CDP_COMMAND_RECV_TIMEOUT:Runtime.evaluate")
        browser = Mock()
        browser.call.side_effect = [
            {"product":"Chrome/1"},
            {"sessionId":"sid-1"},
        ]
        browser.evaluate.return_value = "https://chatgpt.com/c/abc"

        calls=[direct,browser]
        with patch("scripts.gpt_web_response_bridge.CdpPage", side_effect=calls), \
             patch("scripts.gpt_web_response_bridge._browser_ws_url", return_value="ws://browser"):
            endpoint = _open_target_connection("http://127.0.0.1:9222", target)

        self.assertEqual(endpoint.mode, "browser-session")
        self.assertEqual(endpoint.session_id, "sid-1")
        direct.close.assert_called_once()
        endpoint.close()


if __name__ == "__main__":
    unittest.main()
