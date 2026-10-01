from __future__ import annotations

import unittest

from agentos_node.gemini_web_bridge import classify


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


if __name__ == "__main__":
    unittest.main()
