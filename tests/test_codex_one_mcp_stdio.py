from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.codex_one_mcp_stdio import _active_projection, _project_codex_client


class FakeGateway:
    data_root = "/tmp/agent-data"


class CodexOneMcpTests(unittest.TestCase):
    def test_projection_binds_codex_local_surface_without_credentials(self):
        value = _project_codex_client({"schema": "x", "credential_exposed": False})
        self.assertEqual(value["surface"], "codex-local")
        self.assertEqual(value["executor_class"], "openai-codex-local")
        self.assertTrue(value["executor_identity_bound"])
        self.assertEqual(value["executor_identity_source"], "codex-mcp-config")
        self.assertFalse(value["credential_exposed"])

    @patch("agentos_node.codex_one_mcp_stdio.resolve_active_continuation")
    def test_active_projection_uses_one_selector_not_workspace(self, resolve_active):
        resolve_active.return_value = {
            "selector": {
                "project_id": "agentos-core",
                "index_id": "idx-core-152-e3-1",
                "ir_id": "ir-core-152-e3-1",
            },
            "resolution": {
                "schema": "agentos.resolve/v1",
                "project": {"id": "agentos-core"},
                "continuation": {
                    "canonical_ir": {
                        "schema_version": "agentos.ir/v1",
                        "index_id": "idx-core-152-e3-1",
                        "ir_id": "ir-core-152-e3-1",
                    }
                },
            },
        }
        result = _active_projection(FakeGateway())
        resolve_active.assert_called_once_with(data_root="/tmp/agent-data")
        self.assertEqual(result["source"], "ONE_ACTIVE_CONTINUATION")
        self.assertEqual(result["selection_source"], "ONE_ACTIVE_CONTINUATION")
        self.assertEqual(result["selector"]["project_id"], "agentos-core")
        self.assertEqual(result["selector"]["index_id"], "idx-core-152-e3-1")
        self.assertEqual(result["selector"]["ir_id"], "ir-core-152-e3-1")
        self.assertNotIn("workspace", str(result).casefold())

    @patch("agentos_node.codex_one_mcp_stdio.resolve_active_continuation")
    def test_active_resolve_receipt_is_sanitized_and_generation_bound(self, resolve_active):
        resolve_active.return_value = {
            "selector": {
                "project_id": "agentos-core",
                "index_id": "idx-core-152-e3-codex-ext-1",
                "ir_id": "ir-core-152-e3-codex-ext-1",
            },
            "resolution": {"schema": "agentos.resolve/v1"},
        }
        with tempfile.TemporaryDirectory() as td:
            receipt = Path(td) / "receipt.json"
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_CODEX_ONE_RECEIPT_PATH": str(receipt),
                    "AGENTOS_RUNTIME_SOURCE_COMMIT": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                },
                clear=False,
            ):
                _active_projection(FakeGateway(), write_receipt=True)
            record = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(record["schema"], "agentos.codex-one-active-resolve-receipt/v1")
            self.assertEqual(record["runtime_source_commit"], "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
            self.assertEqual(record["project_id"], "agentos-core")
            self.assertEqual(record["index_id"], "idx-core-152-e3-codex-ext-1")
            self.assertEqual(record["ir_id"], "ir-core-152-e3-codex-ext-1")
            self.assertEqual(record["surface"], "codex-local")
            self.assertEqual(record["executor_class"], "openai-codex-local")
            self.assertTrue(record["executor_identity_bound"])
            self.assertFalse(record["credential_exposed"])
            serialized = json.dumps(record, ensure_ascii=False).casefold()
            self.assertNotIn("token", serialized)
            self.assertNotIn("workspace", serialized)


if __name__ == "__main__":
    unittest.main()
