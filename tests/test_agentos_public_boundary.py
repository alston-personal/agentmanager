"""Source-contract checks for candidate public AgentOS presentation routes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AgentOSPublicBoundaryTests(unittest.TestCase):
    def test_public_pages_have_server_metadata_and_no_runtime_fetch(self):
        for page in ("dashboard/app/about/page.tsx", "dashboard/app/agents/page.tsx"):
            source = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertIn("export const metadata", source)
                self.assertIn("<h1", source)
                self.assertNotIn("fetch(", source)
                self.assertNotIn("process.env", source)
                self.assertNotIn("'use client'", source)

    def test_agents_are_allowlisted_and_not_live_status(self):
        source = (ROOT / "dashboard/app/agents/page.tsx").read_text(encoding="utf-8")
        for name in ("The Paw", "The Claw", "LeopardCat Root", "Weaver"):
            self.assertIn(name, source)
        for secret_marker in ("execution_receipt", "node.address", "work-items.json", "/dashboard/api"):
            self.assertNotIn(secret_marker, source)

    def test_operator_root_not_moved_by_public_route_candidate(self):
        source = (ROOT / "dashboard/app/page.tsx").read_text(encoding="utf-8")
        self.assertIn("AI Command Center", source)
        self.assertIn("/dashboard/api/projects", source)


if __name__ == "__main__":
    unittest.main()
