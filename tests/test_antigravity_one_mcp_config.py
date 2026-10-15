"""Offline contract tests for the Antigravity-specific ONE MCP candidate."""
import unittest
from pathlib import Path
from scripts.antigravity_one_mcp_config import merge_config


class AntigravityOneMcpConfigTests(unittest.TestCase):
    def setUp(self):
        self.python = Path("/home/ubuntu/agentmanager/.venv/bin/python")
        self.repo = Path("/home/ubuntu/agentmanager")

    def test_preserve_existing_servers(self):
        source = {"mcpServers": {"unrelated": {"command": "/usr/bin/true"}}, "other": True}
        result = merge_config(source, python=self.python, repo=self.repo)
        self.assertEqual(result["mcpServers"]["unrelated"], source["mcpServers"]["unrelated"])
        self.assertTrue(result["other"])
        one = result["mcpServers"]["agentos-one"]
        self.assertEqual(one["args"], ["-m", "agentos_node.one_mcp", "--mode", "oracle-local"])
        self.assertNotIn("token", str(one).lower())
        self.assertNotIn("hooks", result)
        self.assertNotIn("mcpServers", source if source == {} else {"original": source["mcpServers"]})

    def test_idempotence(self):
        first = merge_config({}, python=self.python, repo=self.repo)
        second = merge_config(first, python=self.python, repo=self.repo)
        self.assertEqual(first, second)

    def test_conflict_fails_closed(self):
        with self.assertRaises(ValueError):
            merge_config({"mcpServers": {"agentos-one": {"serverUrl": "https://elsewhere"}}},
                         python=self.python, repo=self.repo)

    def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            merge_config({}, python=Path("python3"), repo=self.repo)


if __name__ == "__main__":
    unittest.main()
