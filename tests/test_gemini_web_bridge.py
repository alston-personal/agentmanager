from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
