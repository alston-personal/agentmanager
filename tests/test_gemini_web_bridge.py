from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from agentos_node.gemini_web_bridge import classify
from agentos_node.web_agent_surface import WebSurfaceAdapter


class _UnrelatedPage:
    url = "https://example.com/unrelated"

    def locator(self, _selector: str):
        raise AssertionError("unrelated tabs must not be inspected through DOM selectors")

    def title(self):
        raise AssertionError("unrelated tabs must not require page title inspection")


class GeminiWebBridgeClassificationTests(unittest.TestCase):
    def test_unrelated_shared_browser_tab_is_rejected_without_dom_access(self) -> None:
        row = classify(_UnrelatedPage())
        self.assertEqual(row["state"], "UNEXPECTED_DESTINATION")
        self.assertFalse(row["composer_visible"])
        self.assertEqual(row["url"], "https://example.com/unrelated")
        self.assertEqual(row["title"], "")

    def test_playwright_attach_failure_falls_back_to_raw_cdp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = WebSurfaceAdapter(
                provider="gemini-web",
                root=Path(tmp),
                hosts=("gemini.google.com", "accounts.google.com"),
                composer_selectors=(),
                classify=lambda _page: {},
                harvest=lambda _page: [],
                raw_cdp_fallback=True,
            )
            fake_playwright = MagicMock()
            fake_playwright.chromium.connect_over_cdp.side_effect = RuntimeError("attach failed")
            fake_manager = MagicMock()
            fake_manager.start.return_value = fake_playwright
            fake_raw_browser = MagicMock()
            with patch(
                "playwright.sync_api.sync_playwright",
                return_value=fake_manager,
            ), patch(
                "agentos_node.web_agent_surface._RawCDPBrowser.from_endpoint",
                return_value=fake_raw_browser,
            ) as raw:
                client, browser = adapter.with_browser()

            self.assertIs(browser, fake_raw_browser)
            self.assertEqual(client.__class__.__name__, "_RawCDPClient")
            fake_playwright.stop.assert_called_once()
            raw.assert_called_once_with(adapter.cdp_url)
            events = (Path(tmp) / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn('"event":"transport_fallback"', events)

    def test_no_matching_target_writes_fresh_no_session_without_playwright(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = WebSurfaceAdapter(
                provider="gemini-web",
                root=Path(tmp),
                hosts=("gemini.google.com", "accounts.google.com"),
                composer_selectors=(),
                classify=lambda _page: (_ for _ in ()).throw(
                    AssertionError("classify must not run without a matching target")
                ),
                harvest=lambda _page: [],
                preflight_target_inventory=True,
                connect_timeout_ms=5000,
            )
            with patch.object(
                WebSurfaceAdapter,
                "cdp_target_urls",
                return_value=["https://www.threads.com/direct/inbox"],
            ), patch.object(
                WebSurfaceAdapter,
                "with_browser",
                side_effect=AssertionError("Playwright must not start for NO_SESSION"),
            ):
                snapshot = adapter.snapshot_sessions()

            self.assertEqual(snapshot["sessions"], [])
            stored = json.loads((Path(tmp) / "sessions.json").read_text(encoding="utf-8"))
            descriptor = json.loads((Path(tmp) / "bridge.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["sessions"], [])
            self.assertEqual(descriptor["session_state"], "NO_SESSION")

    def test_attach_operation_triggers_on_session_attach_hook(self) -> None:
        from agentos_node.gemini_web_bridge import on_session_attach_hook, BOOTSTRAPPED_SESSIONS
        from agentos_node.session_bridge import REQUEST_SCHEMA

        BOOTSTRAPPED_SESSIONS.clear()
        with tempfile.TemporaryDirectory() as tmp:
            adapter = WebSurfaceAdapter(
                provider="gemini-web",
                root=Path(tmp),
                hosts=("gemini.google.com",),
                composer_selectors=('rich-textarea',),
                classify=lambda _p: {"session_id": "gemini:session-1", "state": "READY", "url": "https://gemini.google.com/app"},
                harvest=lambda _p: [],
                on_session_attach=on_session_attach_hook,
            )

            fake_page = MagicMock()
            fake_composer = MagicMock()
            fake_browser = MagicMock()
            fake_browser.contexts = [MagicMock()]
            fake_browser.contexts[0].pages = [fake_page]
            fake_manager = MagicMock()
            fake_manager.start.return_value.chromium.connect_over_cdp.return_value = fake_browser

            request = {
                "schema": REQUEST_SCHEMA,
                "request_id": "req-attach-1",
                "provider": "gemini-web",
                "operation": "attach",
                "session_id": "gemini:session-1",
            }

            with patch("playwright.sync_api.sync_playwright", return_value=fake_manager), \
                 patch("agentos_node.gemini_web_bridge.first_visible", return_value=fake_composer), \
                 patch("agentos_node.gemini_web_bridge.build_web_executor_preamble", return_value="[AgentOS Hook]"):
                receipt = adapter.process_request(request)

            self.assertTrue(receipt["ok"])
            self.assertEqual(receipt["state"], "ready")
            self.assertIn("bootstrap_hook", receipt["output"])
            self.assertEqual(receipt["output"]["bootstrap_hook"]["status"], "bootstrapped")
            fake_composer.fill.assert_called_once_with("[AgentOS Hook]")
            fake_page.keyboard.press.assert_called_once_with("Enter")
            self.assertIn("gemini:session-1", BOOTSTRAPPED_SESSIONS)

            # Test idempotent: second attach does not re-fill
            with patch("playwright.sync_api.sync_playwright", return_value=fake_manager):
                receipt2 = adapter.process_request(request)
            self.assertEqual(receipt2["output"]["bootstrap_hook"]["status"], "already_bootstrapped")
            self.assertEqual(fake_composer.fill.call_count, 1)


if __name__ == "__main__":
    unittest.main()
