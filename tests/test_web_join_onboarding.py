"""Unit tests for AgentOS Web-Native One-Click Join & Launcher Suite."""
import os
import unittest

class TestWebJoinOnboarding(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.web_join_dir = os.path.join(self.repo_root, "agent_core", "web_join")
        self.html_path = os.path.join(self.web_join_dir, "index.html")
        self.cmd_path = os.path.join(self.web_join_dir, "agentos-join.cmd")
        self.sh_path = os.path.join(self.web_join_dir, "agentos-join.sh")

    def test_web_join_files_exist(self):
        self.assertTrue(os.path.exists(self.html_path), "index.html must exist")
        self.assertTrue(os.path.exists(self.cmd_path), "agentos-join.cmd must exist")
        self.assertTrue(os.path.exists(self.sh_path), "agentos-join.sh must exist")

    def test_html_content_and_download_links(self):
        with open(self.html_path, "r", encoding="utf-8") as f:
            html = f.read()

        self.assertIn("一鍵加入 AgentOS 協同網絡", html)
        self.assertIn("/join/download/windows", html)
        self.assertIn("/join/download/macos-linux", html)
        self.assertIn("Auto Handshake", html)
        self.assertIn("realm-alston", html)
        self.assertIn("curl -sSL https://studio.milkcat.org/join | bash", html)
        self.assertIn("irm https://studio.milkcat.org/join | iex", html)

    def test_windows_launcher_syntax(self):
        with open(self.cmd_path, "r", encoding="utf-8") as f:
            cmd = f.read()

        self.assertIn("@echo off", cmd)
        self.assertIn("powershell", cmd)
        self.assertIn("irm https://studio.milkcat.org/join | iex", cmd)

    def test_unix_launcher_syntax(self):
        with open(self.sh_path, "r", encoding="utf-8") as f:
            sh = f.read()

        self.assertTrue(sh.startswith("#!/bin/bash"), "Shell script must start with shebang")
        self.assertIn("curl -sSL https://studio.milkcat.org/join | bash", sh)

if __name__ == "__main__":
    unittest.main()
