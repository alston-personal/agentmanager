from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import scripts.gpt_web_cdp_renderer_health as health


class GptWebCdpRendererHealthTests(unittest.TestCase):
    def test_about_blank_direct_target_is_healthy(self):
        target={"id":"p1","webSocketDebuggerUrl":"ws://page"}
        direct=Mock()
        direct.evaluate.return_value=2
        with patch.object(health, "_create_target", return_value=target), \
             patch.object(health, "CdpPage", return_value=direct):
            result=health.probe("http://127.0.0.1:9222")
        self.assertTrue(result["ok"])
        self.assertEqual(result["evaluate_result"],2)
        self.assertEqual(result["transport"],"page-ws")

    def test_direct_timeout_falls_back_to_browser_session(self):
        target={"id":"p1","webSocketDebuggerUrl":"ws://page"}
        direct=Mock()
        direct.evaluate.side_effect=TimeoutError("dead page")
        browser=Mock()
        browser.call.return_value={"sessionId":"sid-1"}
        browser.evaluate.return_value=2
        with patch.object(health, "_create_target", return_value=target), \
             patch.object(health, "_browser_ws_url", return_value="ws://browser"), \
             patch.object(health, "CdpPage", side_effect=[direct,browser]):
            result=health.probe("http://127.0.0.1:9222")
        self.assertTrue(result["ok"])
        self.assertEqual(result["evaluate_result"],2)
        self.assertEqual(result["transport"],"browser-session")
        self.assertIn("TimeoutError", result["direct_error"])


if __name__=="__main__":
    unittest.main()
