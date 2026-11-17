import unittest
from agent_core.recon_web import render_recon_html, render_pantheon_html, get_recon_ledger_data

class ReconAndPantheonWebTests(unittest.TestCase):
    def test_render_recon_html(self):
        html = render_recon_html()
        self.assertIn("Hermes Recon Radar", html)
        self.assertIn("開源情資雷達與武器庫", html)
        self.assertIn("/pantheon", html)
        self.assertIn("<!doctype html>", html)

    def test_render_pantheon_html(self):
        html = render_pantheon_html()
        self.assertIn("AgentOS Pantheon", html)
        self.assertIn("系統眾神殿", html)
        self.assertIn("Atlas 阿特拉斯", html)
        self.assertIn("The Paw 神爪", html)
        self.assertIn("The Claw 神鷹", html)
        self.assertIn("Hermes 赫密士", html)
        self.assertIn("Themis 忒彌斯", html)
        self.assertIn("Rhea 瑞亞", html)
        self.assertIn("https://studio.milkcat.org/personas/", html)

if __name__ == "__main__":
    unittest.main()
