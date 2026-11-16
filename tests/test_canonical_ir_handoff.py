from __future__ import annotations

import unittest
from copy import deepcopy
import tempfile
from pathlib import Path
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
    def test_real_publish_and_resolve_preserve_frontier_and_rejected_paths(self):
        from agent_core.project_continuation_index import publish_project_continuation
        from agent_core.resolve_facade import resolve_continuation
        project = {"id": "agentos-core", "identity_source": "governance-directory",
                   "governance_entity_id": "project://agentos-core",
                   "integrity": {"mutation_allowed": True}}
        with tempfile.TemporaryDirectory() as tmp, \
             patch("agent_core.project_continuation_index.resolve_project_identity", return_value=project), \
             patch("agent_core.resolve_facade.resolve_project_identity", return_value=project):
            root = Path(tmp)
            (root / "projects" / "agentos-core").mkdir(parents=True)
            seed = deepcopy(CURRENT)
            ir = seed["continuation"]["canonical_ir"]
            ir["frontier"] = {"active_question": "Which loaded rule caused stopping?"}
            ir["pruned_paths"] = [{"id": "P1", "reason": "Avoid extra agents under user token constraint"}]
            publish_project_continuation({"project_id": "agentos-core",
                                          "execution_head": seed["execution_head"],
                                          "continuation": seed["continuation"]}, data_root=root)
            advance_canonical_ir(request(), data_root=root)
            result = resolve_continuation("agentos-core", data_root=root)["continuation"]["canonical_ir"]
            self.assertEqual(result["frontier"], ir["frontier"])
            self.assertEqual(result["pruned_paths"], ir["pruned_paths"])
            before = (root / "projects/agentos-core/continuity/latest.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "stale handoff"):
                advance_canonical_ir(request(), data_root=root)
            self.assertEqual((root / "projects/agentos-core/continuity/latest.json").read_bytes(), before)

    @patch("agent_core.canonical_ir_handoff.publish_project_continuation")
    @patch("agent_core.canonical_ir_handoff.resolve_continuation")
    def test_semantic_context_survives_two_handoffs_without_mutating_parent(self, resolve, publish):
        current = deepcopy(CURRENT)
        parent = current["continuation"]["canonical_ir"]
        context = {
            "context": {"assumptions": ["Windows rule version is unknown"]},
            "artifacts": [{"uri": "evidence://rule-inspection"}],
            "pruned_paths": [{"id": "P1", "pruned_reason": "User limits token use"}],
            "tensions": [{"id": "T1", "desc": "Continuity versus context size"}],
            "frontier": {"active_question": "Which rules are loaded?", "reasoning_direction": "Inspect provenance"},
        }
        parent.update(deepcopy(context))
        parent["continuation"]["verification"] = {"required": ["Windows acceptance"]}
        original = deepcopy(current)
        resolve.return_value = current
        publish.return_value = {"ok": True}
        req = request()
        del req["pending_tasks"]
        advance_canonical_ir(req)
        first = publish.call_args.args[0]
        child = first["continuation"]["canonical_ir"]
        for key, value in context.items():
            self.assertEqual(child[key], value)
        self.assertEqual(child["pending_tasks"], ["Verify E2"])
        resolve.return_value = first
        advance_canonical_ir(request(expected_index_id=child["index_id"], expected_ir_id=child["ir_id"],
                                     new_index_id="idx-third", new_ir_id="ir-third", pending_tasks=[]))
        grandchild = publish.call_args.args[0]["continuation"]["canonical_ir"]
        for key, value in context.items():
            self.assertEqual(grandchild[key], value)
        self.assertEqual(grandchild["pending_tasks"], [])
        self.assertEqual(grandchild["continuation"]["verification"], {"required": ["Windows acceptance"]})
        grandchild["context"]["assumptions"].append("changed")
        self.assertEqual(child["context"], context["context"])
        self.assertEqual(current, original)

    @patch("agent_core.canonical_ir_handoff.publish_project_continuation")
    @patch("agent_core.canonical_ir_handoff.resolve_continuation")
    def test_rejects_lossy_or_sensitive_parent_before_publish(self, resolve, publish):
        for change in ({"future_semantics": {"must_keep": True}},
                       {"frontier": "wrong shape"},
                       {"decisions": [{"choice": "A", "reason": "evidence"}]},
                       {"context": {"access_token": "test-only-placeholder"}},
                       {"continuation": []}):
            with self.subTest(change=change):
                current = deepcopy(CURRENT)
                current["continuation"]["canonical_ir"].update(change)
                resolve.return_value = current
                with self.assertRaises(ValueError):
                    advance_canonical_ir(request())
                publish.assert_not_called()

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
