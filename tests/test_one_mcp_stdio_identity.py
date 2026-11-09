from __future__ import annotations

import unittest

from agentos_node.one_mcp_stdio import _unbind_executor_identity


class OneMcpStdioIdentityTests(unittest.TestCase):
    def test_status_projection_never_claims_gemini_or_codex(self):
        result = _unbind_executor_identity(
            {
                "schema": "agentos.one-mcp-status/v0.1",
                "surface": "antigravity",
                "executor_class": "antigravity-gemini",
                "connected": True,
            }
        )
        self.assertEqual(result["executor_class"], "antigravity-unbound")
        self.assertFalse(result["executor_identity_bound"])
        self.assertEqual(
            result["executor_identity_source"],
            "preinvocation-hook-required",
        )

    def test_resolve_projection_unbinds_node_context_without_rewriting_ir(self):
        result = _unbind_executor_identity(
            {
                "schema": "agentos.resolve/v1",
                "node_context": {
                    "surface": "antigravity",
                    "executor_class": "antigravity-gemini",
                },
                "continuation": {
                    "canonical_ir": {
                        "schema_version": "agentos.ir/v1",
                        "evidence": [
                            {
                                "kind": "historical",
                                "executor_class": "antigravity-gemini",
                            }
                        ],
                    }
                },
            }
        )
        self.assertEqual(
            result["node_context"]["executor_class"],
            "antigravity-unbound",
        )
        self.assertFalse(result["node_context"]["executor_identity_bound"])
        self.assertEqual(
            result["continuation"]["canonical_ir"]["evidence"][0]["executor_class"],
            "antigravity-gemini",
        )


if __name__ == "__main__":
    unittest.main()
