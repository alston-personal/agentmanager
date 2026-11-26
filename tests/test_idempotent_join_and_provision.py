from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentos_node.onboarding import provision_host_surfaces


class IdempotentJoinAndProvisionTests(unittest.TestCase):
    def test_provision_host_surfaces_creates_gemini_constitution_and_mcp_config(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with mock.patch("agentos_node.onboarding.Path.home", return_value=fake_home):
                summary = provision_host_surfaces(
                    node_id="test-node-1",
                    realm_id="realm-test",
                    config_path=fake_home / "client.json",
                )

                gemini_md = fake_home / ".gemini" / "GEMINI.md"
                self.assertTrue(gemini_md.is_file(), "GEMINI.md should be created")
                content = gemini_md.read_text(encoding="utf-8")
                self.assertIn("AGENTOS_ONE_BOOTSTRAP_START", content)
                self.assertIn("AGENTOS_ONE_BOOTSTRAP_END", content)
                self.assertIn("AgentOS ONE bootstrap", content)
                self.assertIn("test-node-1", content)
                self.assertIn("realm-test", content)

                mcp_cfg = fake_home / ".gemini" / "config" / "mcp_config.json"
                self.assertTrue(mcp_cfg.is_file(), "mcp_config.json should be created")
                cfg_data = json.loads(mcp_cfg.read_text(encoding="utf-8"))
                self.assertIn("agentos-one", cfg_data.get("mcpServers", {}))
                self.assertEqual(cfg_data["mcpServers"]["agentos-one"]["command"], sys.executable)
                self.assertEqual(cfg_data["mcpServers"]["agentos-one"]["args"], ["-m", "agentos_node.one_mcp"])

                self.assertEqual(summary.get("antigravity"), "PROVISIONED")

    def test_provision_host_surfaces_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with mock.patch("agentos_node.onboarding.Path.home", return_value=fake_home):
                summary1 = provision_host_surfaces(
                    node_id="test-node-1",
                    realm_id="realm-test",
                )
                summary2 = provision_host_surfaces(
                    node_id="test-node-1",
                    realm_id="realm-test",
                )
                self.assertEqual(summary1.get("antigravity"), "PROVISIONED")
                self.assertEqual(summary2.get("antigravity"), "PROVISIONED")

                gemini_md = fake_home / ".gemini" / "GEMINI.md"
                content = gemini_md.read_text(encoding="utf-8")
                # Bootstrap marker should only appear once
                self.assertEqual(content.count("AGENTOS_ONE_BOOTSTRAP_START"), 1)


if __name__ == "__main__":
    unittest.main()
