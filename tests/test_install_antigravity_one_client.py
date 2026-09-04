from __future__ import annotations

import json
import inspect
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

    def test_installer_probe_and_lifecycle_use_separate_audits(self):
        source = inspect.getsource(installer.main)
        self.assertIn("antigravity-preinvocation-installer-probe.json", source)
        self.assertIn("antigravity-preinvocation-last.json", source)
        self.assertLess(
            source.index("probe_launcher = write_hook_launcher"),
            source.index("hook_launcher = write_hook_launcher"),
        )

    def test_windows_probe_executes_the_managed_cmd_launcher(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            completed = mock.Mock(returncode=0, stderr="")
            completed.stdout = json.dumps(
                {
                    "injectSteps": [
                        {
                            "ephemeralMessage": (
                                "ONE_PREINVOCATION_IR\n"
                                + json.dumps(
                                    {
                                        "selection_source": "ONE_ACTIVE_CONTINUATION",
                                        "executor_class": "antigravity-gemini",
                                        "executor_identity_bound": True,
                                        "credential_exposed": False,
                                        "active_selector": {
                                            "project_id": "agentos-core",
                                            "index_id": "idx-1",
                                            "ir_id": "ir-1",
                                        },
                                        "canonical_ir": {
                                            "index_id": "idx-1",
                                            "ir_id": "ir-1",
                                        },
                                    }
                                )
                            )
                        }
                    ]
                }
            )
            launcher = root / "state path" / "hook.cmd"
            with (
                mock.patch.object(installer.os, "name", "nt"),
                mock.patch.dict(installer.os.environ, {"COMSPEC": "cmd.exe"}),
                mock.patch.object(installer.subprocess, "run", return_value=completed) as run,
            ):
                evidence = installer.probe_preinvocation_hook(
                    root / "python.exe",
                    root,
                    client_config=root / "client.json",
                    audit_path=root / "audit.json",
                    launcher=launcher,
                )
            self.assertEqual(evidence["execution"], "windows-cmd-launcher")
            self.assertEqual(
                run.call_args.args[0],
                f'call "{launcher}"',
            )
            self.assertIs(run.call_args.kwargs["shell"], True)
            self.assertEqual(run.call_args.kwargs["executable"], "cmd.exe")


if __name__ == "__main__":
    unittest.main()
