from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.claude_one_mcp_stdio import _active_projection, _project_claude_client


class FakeGateway:
    data_root = "/tmp/agent-data"


class ClaudeOneMcpTests(unittest.TestCase):
    def test_projection_separates_surface_from_backend_identity(self):
        with patch.dict(os.environ, {}, clear=True):
            value = _project_claude_client({"schema": "x", "credential_exposed": False})
        self.assertEqual(value["surface"], "anthropic-claude-code-extension")
        self.assertEqual(value["executor_adapter"], "claude-code-extension-adapter")
        self.assertEqual(value["executor_class"], "anthropic-claude-code-local")
        self.assertTrue(value["executor_identity_bound"])
        self.assertEqual(value["executor_identity_source"], "claude-user-mcp-config")
        self.assertEqual(value["backend_class"], "unknown")
        self.assertEqual(value["backend_identity"], "unknown")
        self.assertFalse(value["backend_identity_bound"])
        self.assertIsNone(value["backend_identity_source"])
        self.assertFalse(value["credential_exposed"])

    def test_trusted_local_backend_identity_is_explicit_not_surface_inferred(self):
        with patch.dict(
            os.environ,
            {"AGENTOS_CLAUDE_BACKEND_CLASS": "local-model", "AGENTOS_CLAUDE_BACKEND_ID": "ollama/qwen3-coder"},
            clear=True,
        ):
            value = _project_claude_client({"schema": "x"})
        self.assertEqual(value["backend_class"], "local-model")
        self.assertEqual(value["backend_identity"], "ollama/qwen3-coder")
        self.assertTrue(value["backend_identity_bound"])
        self.assertEqual(value["backend_identity_source"], "trusted-local-config")

    @patch("agentos_node.claude_one_mcp_stdio.resolve_active_continuation")
    def test_active_projection_uses_one_selector_not_workspace(self, resolve_active):
        resolve_active.return_value = {
            "selector": {
                "project_id": "agentos-core",
                "index_id": "idx-core-185-1",
                "ir_id": "ir-core-185-1",
            },
            "resolution": {"schema": "agentos.resolve/v1", "project": {"id": "agentos-core"}},
        }
        with patch.dict(os.environ, {}, clear=True):
            result = _active_projection(FakeGateway())
        resolve_active.assert_called_once_with(data_root="/tmp/agent-data")
        self.assertEqual(result["source"], "ONE_ACTIVE_CONTINUATION")
        self.assertEqual(result["selection_source"], "ONE_ACTIVE_CONTINUATION")
        self.assertEqual(result["selector"]["project_id"], "agentos-core")
        self.assertEqual(result["selector"]["index_id"], "idx-core-185-1")
        self.assertEqual(result["selector"]["ir_id"], "ir-core-185-1")
        self.assertNotIn("workspace", json.dumps(result).casefold())

    @patch("agentos_node.claude_one_mcp_stdio.resolve_active_continuation")
    def test_active_resolve_receipt_is_sanitized_generation_and_backend_bound(self, resolve_active):
        resolve_active.return_value = {
            "selector": {
                "project_id": "agentos-core",
                "index_id": "idx-core-185-1",
                "ir_id": "ir-core-185-1",
            },
            "resolution": {"schema": "agentos.resolve/v1"},
        }
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_CLAUDE_ONE_RECEIPT_PATH": str(receipt),
                    "AGENTOS_RUNTIME_SOURCE_COMMIT": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                    "AGENTOS_CLAUDE_BACKEND_CLASS": "local-model",
                },
                clear=True,
            ):
                _active_projection(FakeGateway(), write_receipt=True)
            record = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(record["schema"], "agentos.claude-extension-one-active-resolve-receipt/v1")
            self.assertEqual(record["runtime_source_commit"], "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
            self.assertEqual(record["project_id"], "agentos-core")
            self.assertEqual(record["index_id"], "idx-core-185-1")
            self.assertEqual(record["ir_id"], "ir-core-185-1")
            self.assertEqual(record["surface"], "anthropic-claude-code-extension")
            self.assertEqual(record["executor_adapter"], "claude-code-extension-adapter")
            self.assertEqual(record["backend_class"], "local-model")
            self.assertEqual(record["backend_identity"], "unknown")
            self.assertFalse(record["backend_identity_bound"])
            self.assertFalse(record["credential_exposed"])
            serialized = json.dumps(record, ensure_ascii=False).casefold()
            self.assertNotIn("workspace", serialized)
            self.assertNotIn("prompt", serialized)
            self.assertNotIn("session", serialized)
            self.assertNotIn("credential", serialized.replace('"credential_exposed": false', ""))

    def test_backend_identity_rejects_unbounded_or_secret_like_text(self):
        with patch.dict(os.environ, {"AGENTOS_CLAUDE_BACKEND_ID": "local model with spaces"}, clear=True):
            with self.assertRaises(ValueError):
                _project_claude_client({"schema": "x"})


if __name__ == "__main__":
    unittest.main()
