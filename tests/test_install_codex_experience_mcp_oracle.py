from __future__ import annotations

from pathlib import Path
import unittest

from scripts.install_codex_experience_mcp_oracle import CONFIG_START, CONFIG_END, block, replace_block


class InstallCodexExperienceMcpTests(unittest.TestCase):
    def test_block_contains_runtime_wiring_not_experience_body(self):
        text = block(Path("/tmp/python"))
        self.assertIn('[mcp_servers."agentos-experience"]', text)
        self.assertIn("agentos_node.experience_mcp_stdio", text)
        self.assertIn("AGENT_DATA_ROOT", text)
        self.assertNotIn("core/integration", text)
        self.assertNotIn("generic_continue", text)
        self.assertNotIn("experience_ids", text)
        self.assertNotIn("credential", text.casefold())

    def test_managed_block_replaces_itself_and_preserves_other_config(self):
        original = 'model = "x"\n\n' + block(Path("/old/python")) + '\n\n[features]\nfoo = true\n'
        updated = replace_block(original, block(Path("/new/python")))
        self.assertEqual(updated.count(CONFIG_START), 1)
        self.assertEqual(updated.count(CONFIG_END), 1)
        self.assertIn("/new/python", updated)
        self.assertNotIn("/old/python", updated)
        self.assertIn('model = "x"', updated)
        self.assertIn("[features]", updated)

    def test_unmanaged_same_server_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            replace_block('[mcp_servers."agentos-experience"]\nenabled=true\n', block(Path("/tmp/python")))


if __name__ == "__main__":
    unittest.main()
