from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.install_claude_one_oracle import (
    BOOTSTRAP_BLOCK,
    SERVER_NAME,
    _mcp_payload,
    install_user_mcp,
    write_bootstrap,
)


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class InstallClaudeOneOracleTests(unittest.TestCase):
    def test_bootstrap_resolves_one_before_workspace_and_separates_backend_identity(self):
        text = BOOTSTRAP_BLOCK
        self.assertIn("agentos-one.one_resolve_active", text)
        self.assertLess(text.index("agentos-one.one_resolve_active"), text.index("Do not infer the current project from the IDE workspace"))
        self.assertIn("Do not infer backend/model identity from the Claude Code extension surface", text)
        self.assertNotIn("idx-core-", text)
        self.assertNotIn("ir-core-", text)

    def test_bootstrap_managed_block_preserves_unmanaged_content(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "CLAUDE.md"
            path.write_text("# Personal preferences\nKeep this.\n", encoding="utf-8")
            write_bootstrap(path)
            first = path.read_text(encoding="utf-8")
            self.assertIn("Keep this.", first)
            self.assertEqual(first.count("AGENTOS_ONE_CLAUDE_BOOTSTRAP_START"), 1)
            write_bootstrap(path)
            second = path.read_text(encoding="utf-8")
            self.assertIn("Keep this.", second)
            self.assertEqual(second.count("AGENTOS_ONE_CLAUDE_BOOTSTRAP_START"), 1)

    def test_mcp_payload_uses_readonly_one_module_without_credentials_or_ir_body(self):
        with patch.dict(
            os.environ,
            {
                "AGENT_DATA_ROOT": "/srv/agent-data",
                "AGENTOS_CLAUDE_BACKEND_CLASS": "local-model",
                "AGENTOS_CLAUDE_BACKEND_ID": "ollama/qwen3-coder",
            },
            clear=True,
        ):
            payload = _mcp_payload(python=Path("/venv/bin/python"), repo_root=Path("/runtime/snapshot"))
        self.assertEqual(payload["type"], "stdio")
        self.assertEqual(payload["command"], "/venv/bin/python")
        self.assertEqual(payload["args"], ["-m", "agentos_node.claude_one_mcp_stdio"])
        env = payload["env"]
        self.assertEqual(env["AGENT_DATA_ROOT"], "/srv/agent-data")
        self.assertEqual(env["AGENTOS_CLAUDE_BACKEND_CLASS"], "local-model")
        serialized = json.dumps(payload, ensure_ascii=False).casefold()
        for forbidden in ("canonical_ir", "bearer", "password", "secret", "auth_token"):
            self.assertNotIn(forbidden, serialized)

    def test_existing_unmanaged_server_fails_closed(self):
        with tempfile.TemporaryDirectory() as td, patch("pathlib.Path.home", return_value=Path(td)):
            with patch("scripts.install_claude_one_oracle._run", return_value=FakeResult(returncode=0, stdout="exists")):
                with self.assertRaisesRegex(ValueError, "unmanaged Claude MCP server"):
                    install_user_mcp(Path("/fake/claude"), python=Path("/venv/python"), repo_root=Path("/runtime"))

    def test_missing_server_is_added_at_user_scope_and_marker_is_private(self):
        calls: list[list[str]] = []

        def fake_run(args: list[str], *, timeout: float = 20.0):
            calls.append(args)
            if args[1:4] == ["mcp", "get", SERVER_NAME]:
                return FakeResult(returncode=1, stderr="not found")
            return FakeResult(returncode=0, stdout="added")

        with tempfile.TemporaryDirectory() as td, patch("pathlib.Path.home", return_value=Path(td)):
            with patch("scripts.install_claude_one_oracle._run", side_effect=fake_run):
                result = install_user_mcp(
                    Path("/fake/claude"), python=Path("/venv/python"), repo_root=Path("/runtime/snapshot")
                )
            self.assertTrue(result["managed"])
            add = calls[1]
            self.assertEqual(add[:6], ["/fake/claude", "mcp", "add-json", "--scope", "user", SERVER_NAME])
            marker = Path(td) / ".local" / "share" / "agentos" / "claude-one" / "managed-mcp.json"
            self.assertTrue(marker.is_file())
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            saved = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(saved["server"], SERVER_NAME)

    def test_existing_owned_same_payload_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td, patch("pathlib.Path.home", return_value=Path(td)):
            home = Path(td)
            marker = home / ".local" / "share" / "agentos" / "claude-one" / "managed-mcp.json"
            marker.parent.mkdir(parents=True)
            with patch.dict(os.environ, {}, clear=True):
                payload = _mcp_payload(python=Path("/venv/python"), repo_root=Path("/runtime/snapshot"))
            marker.write_text(
                json.dumps({"schema": "agentos.claude-one-managed-mcp/v1", "server": SERVER_NAME, "payload": payload}),
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_run(args: list[str], *, timeout: float = 20.0):
                calls.append(args)
                return FakeResult(returncode=0, stdout="exists")

            with patch.dict(os.environ, {}, clear=True), patch("scripts.install_claude_one_oracle._run", side_effect=fake_run):
                result = install_user_mcp(
                    Path("/fake/claude"), python=Path("/venv/python"), repo_root=Path("/runtime/snapshot")
                )
            self.assertTrue(result["already_present"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1:4], ["mcp", "get", SERVER_NAME])


if __name__ == "__main__":
    unittest.main()
