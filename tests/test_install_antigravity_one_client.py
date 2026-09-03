from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import install_antigravity_one_mcp as installer


class InstallAntigravityOneClientTests(unittest.TestCase):
    def test_empty_existing_json_config_is_treated_as_unconfigured(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "mcp_config.json"
            path.write_text("\ufeff  \r\n\t", encoding="utf-8")
            self.assertEqual(installer._load_json(path), {})

    def test_malformed_nonempty_json_config_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "mcp_config.json"
            path.write_text('{"mcpServers":', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                installer._load_json(path)

    def test_nonobject_json_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "mcp_config.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer._load_json(path)

    def test_windows_hook_launcher_keeps_credential_out_of_config(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = root / "state"
            python = root / "venv" / "Scripts" / "python.exe"
            repo = root / "source tree"
            client = state / "client.json"
            audit = state / "mcp" / "antigravity-preinvocation-last.json"
            with mock.patch.object(installer.os, "name", "nt"):
                launcher = installer.write_hook_launcher(
                    state,
                    python=python,
                    repo_root=repo,
                    client_config=client,
                    audit_path=audit,
                )
                hook = installer.write_hooks_config(
                    root / ".gemini" / "config" / "hooks.json",
                    launcher=launcher,
                )
            text = launcher.read_text(encoding="utf-8")
            serialized = json.dumps(hook)
            self.assertIn("AGENTOS_ONE_MCP_MODE=client", text)
            self.assertIn("AGENTOS_CLIENT_CONFIG=", text)
            self.assertIn("antigravity_one_hook", text)
            self.assertNotIn("node_token", serialized)
            self.assertNotIn("TOPSECRET", serialized)
            self.assertEqual(hook["PreInvocation"][0]["timeout"], 12)

    def test_global_rule_requires_dynamic_preinvocation(self):
        self.assertIn("PreInvocation", installer.GLOBAL_RULE)
        self.assertIn("one_resolve_active", installer.GLOBAL_RULE)
        self.assertIn("workspace is environment metadata", installer.GLOBAL_RULE)


if __name__ == "__main__":
    unittest.main()

