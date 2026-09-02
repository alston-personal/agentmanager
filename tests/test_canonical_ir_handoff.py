from __future__ import annotations

import unittest
from unittest.mock import patch

from agent_core.canonical_ir_handoff import advance_canonical_ir


CURRENT = {
    "schema": "agentos.resolve/v1",
    "execution_head": {
        "schema": "agentos.execution-head/v1",
        "index_id": "idx-core-152",
    },
    "continuation": {
        "canonical_ir": {
            "schema_version": "agentos.ir/v1",
            "index_id": "idx-core-152",
            "ir_id": "ir-core-152",
            "parent_ir_id": None,
            "goal": "Complete E2",
            "constraints": ["Preserve credential isolation"],
            "decisions": ["Use ONE_PREINVOCATION_IR"],
            "pending_tasks": ["Verify E2"],
            "evidence": [],
            "continuation": {"recommended_action": "Verify E2"},
            "capability": "agentos.one.resolve",
        }
    },
}


def request(**overrides):
    value = {
        "project_id": "agentos-core",
        "expected_index_id": "idx-core-152",
        "expected_ir_id": "ir-core-152",
        "new_index_id": "idx-core-152-e3",
        "new_ir_id": "ir-core-152-e3",
        "goal": "Prove Gemini -> ONE -> fresh Antigravity Codex continuity",
        "next_action": "Open a fresh Antigravity Codex conversation and send only 繼續",
        "pending_tasks": ["Run fresh Codex regression"],
        "decisions_append": ["E2 Antigravity Gemini fresh IR continuity is verified"],
        "evidence": [
            {
                "kind": "live-regression",
                "verdict": "VERIFIED",
                "summary": "Two independent fresh Gemini sessions recovered the same canonical IR",
            }
        ],
        "execution_status": "in_progress",
        "execution_metadata": {"issue": "#152", "phase": "E3"},
    }
    value.update(overrides)
    return value


class CanonicalIrHandoffTests(unittest.TestCase):
    @patch("agent_core.canonical_ir_handoff.publish_project_continuation")
    @patch("agent_core.canonical_ir_handoff.resolve_continuation")
    def test_builds_child_generation_and_preserves_authoritative_context(self, resolve, publish):
        resolve.return_value = CURRENT
        publish.return_value = {"ok": True, "schema": "agentos.project-continuation-publish/v1"}
        receipt = advance_canonical_ir(request())
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["parent"]["ir_id"], "ir-core-152")
        self.assertEqual(receipt["child"]["ir_id"], "ir-core-152-e3")
        params = publish.call_args.args[0]
        ir = params["continuation"]["canonical_ir"]
        self.assertEqual(ir["parent_ir_id"], "ir-core-152")
        self.assertIn("Preserve credential isolation", ir["constraints"])
        self.assertIn("Use ONE_PREINVOCATION_IR", ir["decisions"])
        self.assertIn("E2 Antigravity Gemini fresh IR continuity is verified", ir["decisions"])
        self.assertEqual(ir["evidence"][0]["verdict"], "VERIFIED")
        self.assertEqual(publish.call_args.kwargs["expected_index_id"], "idx-core-152")
        self.assertEqual(publish.call_args.kwargs["expected_ir_id"], "ir-core-152")

    @patch("agent_core.canonical_ir_handoff.publish_project_continuation")
    @patch("agent_core.canonical_ir_handoff.resolve_continuation")
    def test_rejects_stale_request_before_publish(self, resolve, publish):
        current = {
            **CURRENT,
            "execution_head": {"schema": "agentos.execution-head/v1", "index_id": "idx-newer"},
            "continuation": {
                "canonical_ir": {
                    **CURRENT["continuation"]["canonical_ir"],
                    "index_id": "idx-newer",
                    "ir_id": "ir-newer",
                }
            },
        }
        resolve.return_value = current
        with self.assertRaisesRegex(ValueError, "stale handoff request"):
            advance_canonical_ir(request())
        publish.assert_not_called()

    def test_rejects_sensitive_evidence(self):
        with self.assertRaisesRegex(ValueError, "sensitive credential"):
            advance_canonical_ir(
                request(
                    evidence=[
                        {
                            "kind": "probe",
                            "verdict": "PASS",
                            "summary": "bad evidence",
                            "token": "must-not-enter-ir",
                        }
                    ]
                )
            )

    def test_rejects_non_core_project(self):
        with self.assertRaisesRegex(ValueError, "restricted to agentos-core"):
            advance_canonical_ir(request(project_id="other"))


if __name__ == "__main__":
    unittest.main()
