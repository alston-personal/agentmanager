from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agentos_node.experience_mcp_stdio import one_experience_hydrate


class ExperienceMcpTests(unittest.TestCase):
    def test_hydration_receipt_is_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = root / "runtime" / "receipt.json"
            projection = {
                "schema": "agentos.experience-hydration/v0",
                "project_id": "agentos-core",
                "active_goal": "secret prompt text must not be copied",
                "experience_ids": ["a", "b"],
                "items": [{"summary": "sensitive-ish model visible experience"}],
                "digest": "abc",
                "source": "ONE_EXPERIENCE",
                "credential_exposed": False,
            }
            with patch("agentos_node.experience_mcp_stdio.hydrate_from_one", return_value=projection), patch.dict(
                os.environ,
                {
                    "AGENT_DATA_ROOT": str(root),
                    "AGENTOS_EXPERIENCE_HYDRATION_RECEIPT": str(receipt),
                    "AGENTOS_RUNTIME_SOURCE_COMMIT": "deadbeef",
                },
                clear=False,
            ):
                result = one_experience_hydrate("agentos-core", "secret prompt text must not be copied")
            self.assertEqual(result["source"], "ONE_EXPERIENCE")
            stored = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(stored["project_id"], "agentos-core")
            self.assertEqual(stored["projection_digest"], "abc")
            self.assertEqual(stored["experience_ids"], ["a", "b"])
            self.assertEqual(stored["executor_class"], "openai-codex-local")
            self.assertFalse(stored["credential_exposed"])
            raw = receipt.read_text(encoding="utf-8")
            self.assertNotIn("secret prompt", raw)
            self.assertNotIn("sensitive-ish", raw)
            self.assertNotIn("items", stored)


if __name__ == "__main__":
    unittest.main()
