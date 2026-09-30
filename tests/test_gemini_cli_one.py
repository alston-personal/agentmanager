import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agentos_node import gemini_cli_one_hook
from scripts import install_gemini_cli_one


class FakeGateway:
    def status(self):
        return {"connected": True, "schema": "agentos.one-mcp-status/v0.1"}

    def resolve(self, project):
        return {
            "schema": "agentos.resolve/v1",
            "project": {"id": project},
            "active_goal": "continue agentos",
            "mutation_allowed": False,
            "execution_head": {"schema": "agentos.execution-head/v1", "index_id": "idx-1", "active_goal": "continue agentos"},
            "continuation": {
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": "idx-1",
                    "ir_id": "ir-1",
                    "goal": "continue agentos",
                    "constraints": ["no secrets"],
                    "decisions": ["reuse ONE"],
                    "pending_tasks": ["gemini cli"],
                }
            },
            "next_action": "implement cli adapter",
        }


class GeminiCliOneTests(unittest.TestCase):
    def test_session_start_hydrates_compact_ir(self):
        out = gemini_cli_one_hook.build_session_start(
            {"hook_event_name": "SessionStart", "source": "startup"},
            gateway=FakeGateway(),
            selector={"project_id": "agentos-core", "index_id": "idx-1", "ir_id": "ir-1"},
        )
        text = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("ONE_SESSIONSTART_IR", text)
        self.assertIn("agentos-core", text)
        self.assertIn("ir-1", text)
        self.assertNotIn("token", text.casefold())

    def test_installer_merges_mcp_and_sessionstart_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / "settings.json"
            python = root / "python"
            python.write_text("", encoding="utf-8")
            config = install_gemini_cli_one.merge_settings(
                settings,
                python=python,
                root=root,
                mode="oracle-local",
            )
            self.assertIn("agentos-one", config["mcpServers"])
            self.assertIn("SessionStart", config["hooks"])
            serialized = json.dumps(config)
            self.assertNotIn("node_token", serialized)
            self.assertNotIn("access_token", serialized)
            self.assertIn("gemini_cli_one_hook", serialized)


if __name__ == "__main__":
    unittest.main()
