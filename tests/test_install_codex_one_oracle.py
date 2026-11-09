from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install_codex_one_oracle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("install_codex_one_oracle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class InstallCodexOneOracleTests(unittest.TestCase):
    def test_agents_block_requires_one_resolve_active_before_workspace_reconstruction(self):
        module = _load_module()
        text = module.AGENTS_BLOCK
        self.assertIn("agentos-one.one_resolve_active", text)
        self.assertIn("IDE workspace", text)
        self.assertIn("ONE_ACTIVE_CONTINUATION_UNRESOLVED", text)
        self.assertNotIn("idx-core-152", text)
        self.assertNotIn("ir-core-152", text)

    def test_config_block_registers_codex_specific_mcp_without_credentials(self):
        module = _load_module()
        block = module.config_block(
            python=Path("/runtime/venv/bin/python"),
            repo_root=Path("/runtime/snapshot"),
        )
        self.assertIn('[mcp_servers."agentos-one"]', block)
        self.assertIn("agentos_node.codex_one_mcp_stdio", block)
        self.assertIn("AGENTOS_ONE_MCP_MODE = \"oracle-local\"", block)
        self.assertNotIn("token", block.casefold())
        self.assertNotIn("password", block.casefold())

    def test_managed_blocks_preserve_unmanaged_content(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            agents = root / "AGENTS.md"
            agents.write_text("existing instructions\n", encoding="utf-8")
            module.write_agents(agents)
            updated = agents.read_text(encoding="utf-8")
            self.assertIn("existing instructions", updated)
            self.assertEqual(updated.count(module.AGENTS_START), 1)
            self.assertEqual(updated.count(module.AGENTS_END), 1)

    def test_unmanaged_same_name_mcp_fails_closed(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.toml"
            path.write_text('[mcp_servers."agentos-one"]\ncommand = "other"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unmanaged Codex agentos-one MCP"):
                module.write_config(
                    path,
                    python=Path("/runtime/venv/bin/python"),
                    repo_root=Path("/runtime/snapshot"),
                )


if __name__ == "__main__":
    unittest.main()
