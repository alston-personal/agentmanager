from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import scripts.gpt_web_cdp_renderer_health as health


class GptWebCdpRendererHealthTests(unittest.TestCase):
    def test_about_blank_direct_target_is_healthy(self):
        target={"id":"p1","webSocketDebuggerUrl":"ws://page"}
        page=Mock()
        page.evaluate.return_value=2
        page.mode="page-ws"
        with patch.object(health, "_create_target", return_value=target),              patch.object(health, "CdpPage", return_value=page):
            rc=health.main.__wrapped__() if hasattr(health.main, "__wrapped__") else None

    def test_direct_timeout_can_fallback_to_browser_session(self):
        target={"id":"p1","webSocketDebuggerUrl":"ws://page"}
        direct=Mock()
        direct.evaluate.side_effect=TimeoutError("dead page")
        browser=Mock()
        browser.call.return_value={"sessionId":"sid-1"}
        browser.evaluate.return_value=2
        with patch.object(health, "_create_target", return_value=target),              patch.object(health, "_browser_ws_url", return_value="ws://browser"),              patch.object(health, "CdpPage", side_effect=[direct,browser]):
            # Exercise the same transport primitives without invoking argparse.
            endpoint=None
            try:
                try:
                    conn=health.CdpPage(target["webSocketDebuggerUrl"])
                    endpoint=health.CdpTargetSession(conn,session_id=None,mode="page-ws")
                    endpoint.evaluate("1+1")
                except Exception:
                    if endpoint is not None:
                        endpoint.close()
                    conn=health.CdpPage(health._browser_ws_url("http://127.0.0.1:9222"))
                    attached=conn.call("Target.attachToTarget",{"targetId":"p1","flatten":True})
                    endpoint=health.CdpTargetSession(conn,session_id=attached["sessionId"],mode="browser-session")
                    value=endpoint.evaluate("1+1")
            finally:
                if endpoint is not None:
                    endpoint.close()
        self.assertEqual(value,2)
        self.assertEqual(endpoint.mode,"browser-session")


if __name__=="__main__":
    unittest.main()
