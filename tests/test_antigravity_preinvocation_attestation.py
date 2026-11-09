from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.antigravity_one_hook import _write_attestation


class AntigravityPreInvocationAttestationTests(unittest.TestCase):
    def test_hydration_attestation_is_sanitized_and_generation_bound(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "last.json"
            payload = {
                "invocationNum": 0,
                "conversationId": "vendor-conversation-secret-ish-id",
                "workspacePaths": ["/home/ubuntu/acas"],
                "modelName": "gpt-5-codex",
            }
            envelope = {
                "source": "ONE_PREINVOCATION_IR",
                "selection_source": "ONE_ACTIVE_CONTINUATION",
                "active_selector": {
                    "project_id": "agentos-core",
                    "index_id": "idx-core-152-e3-1",
                    "ir_id": "ir-core-152-e3-1",
                },
                "executor_class": "antigravity-codex",
                "executor_identity_bound": True,
            }
            with patch.dict(
                os.environ,
                {
                    "AGENTOS_PREINVOCATION_AUDIT_PATH": str(path),
                    "AGENTOS_RUNTIME_SOURCE_COMMIT": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                },
                clear=False,
            ):
                _write_attestation(payload, envelope, outcome="hydrated")

            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["schema"], "agentos.antigravity-preinvocation-attestation/v1")
            self.assertEqual(record["runtime_source_commit"], "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
            self.assertEqual(record["outcome"], "hydrated")
            self.assertTrue(record["injection_emitted"])
            self.assertEqual(record["selection_source"], "ONE_ACTIVE_CONTINUATION")
            self.assertEqual(record["project_id"], "agentos-core")
            self.assertEqual(record["index_id"], "idx-core-152-e3-1")
            self.assertEqual(record["ir_id"], "ir-core-152-e3-1")
            self.assertEqual(record["executor_class"], "antigravity-codex")
            self.assertTrue(record["executor_identity_bound"])
            self.assertTrue(str(record["conversation_id_sha256"]).startswith("sha256:"))
            serialized = json.dumps(record, ensure_ascii=False)
            self.assertNotIn("vendor-conversation-secret-ish-id", serialized)
            self.assertNotIn("/home/ubuntu/acas", serialized)
            self.assertNotIn("workspacePaths", serialized)
            self.assertNotIn("token", serialized.casefold())
            self.assertFalse(record["credential_exposed"])

    def test_later_invocation_does_not_overwrite_attestation(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "last.json"
            path.write_text('{"sentinel": true}\n', encoding="utf-8")
            with patch.dict(
                os.environ,
                {"AGENTOS_PREINVOCATION_AUDIT_PATH": str(path)},
                clear=False,
            ):
                _write_attestation(
                    {"invocationNum": 1, "conversationId": "later", "modelName": "gpt-5-codex"},
                    None,
                    outcome="no-injection",
                )
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"sentinel": True})


if __name__ == "__main__":
    unittest.main()
