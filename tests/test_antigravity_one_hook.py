from __future__ import annotations

import json
import unittest

from agentos_node.antigravity_one_hook import build_injection


class FakeGateway:
    def __init__(self, *, index_id="idx-7"):
        self.resolved = []
        self.index_id = index_id

    def status(self):
        return {
            "schema": "agentos.one-mcp-status/v0.1",
            "connected": True,
            "realm_id": "realm-test",
            "node_id": "oracle-core-node",
        }

    def resolve(self, project):
        self.resolved.append(project)
        return {
            "schema": "agentos.resolve/v1",
            "project": {"id": "agentos-core", "name": "AgentOS Core"},
            "mutation_allowed": False,
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": self.index_id,
                "active_goal": "Complete #152 Antigravity IR hydration",
                "execution_head": {"status": "in_progress"},
            },
            "continuation": {
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": self.index_id,
                    "ir_id": "ir-core-152",
                    "parent_ir_id": "ir-core-151",
                    "goal": "Complete #152 Antigravity IR hydration",
                    "constraints": ["Do not infer current state from workspace order"],
                    "decisions": ["Canonical IR is the durable continuation state"],
                    "pending_tasks": ["Run fresh Gemini regression"],
                    "continuation": {"recommended_action": "Run fresh Gemini regression"},
                    "capability": "agentos.one.resolve",
                }
            },
            "next_action": "Run fresh Gemini regression",
            "provenance": {"continuation": "project/continuity/latest.json"},
        }


def envelope_from(output):
    message = output["injectSteps"][0]["ephemeralMessage"]
    return json.loads(message.split("\n", 1)[1])


class AntigravityOneHookTests(unittest.TestCase):
    def test_first_invocation_hydrates_single_canonical_ir(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": [
                    "/home/ubuntu/zeus-writer",
                    "/home/ubuntu/agentmanager",
                    "/home/ubuntu/privacy-guard",
                ],
                "modelName": "gemini-test",
            },
            gateway,
        )
        self.assertIn("injectSteps", output)
        message = output["injectSteps"][0]["ephemeralMessage"]
        self.assertIn("ONE_PREINVOCATION_IR", message)
        self.assertIn("ir-core-152", message)
        self.assertIn("idx-7", message)
        self.assertIn("Complete #152 Antigravity IR hydration", message)
        self.assertNotIn("zeus-writer", message)
        self.assertNotIn("privacy-guard", message)
        self.assertNotIn("token", message.casefold())
        self.assertEqual(gateway.resolved, ["agentos-core"])
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-gemini")
        self.assertTrue(envelope["executor_identity_bound"])

    def test_nested_workspace_under_agentmanager_hydrates_core_ir(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": [
                    "/home/ubuntu/agentmanager/workspace/if-tv-station",
                ],
                "modelName": "gpt-5-codex",
            },
            gateway,
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["canonical_ir"]["project_id"], "agentos-core")
        self.assertEqual(envelope["executor_class"], "antigravity-codex")
        self.assertEqual(gateway.resolved, ["agentos-core"])
        self.assertNotIn("if-tv-station", json.dumps(envelope))

    def test_prefix_lookalike_workspace_does_not_open_core_gate(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": [
                    "/home/ubuntu/agentmanager-old/workspace/if-tv-station",
                ],
                "modelName": "gpt-5-codex",
            },
            gateway,
        )
        self.assertEqual(output, {})
        self.assertEqual(gateway.resolved, [])

    def test_codex_model_binds_codex_executor(self):
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/agentmanager"],
                "modelName": "gpt-5-codex",
            },
            FakeGateway(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-codex")
        self.assertTrue(envelope["executor_identity_bound"])
        self.assertEqual(envelope["model_name"], "gpt-5-codex")

    def test_unknown_model_does_not_guess_executor_identity(self):
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/agentmanager"],
                "modelName": "mystery-model",
            },
            FakeGateway(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-unknown")
        self.assertFalse(envelope["executor_identity_bound"])

    def test_later_invocation_is_silent(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 1,
                "workspacePaths": ["/home/ubuntu/agentmanager"],
            },
            gateway,
        )
        self.assertEqual(output, {})
        self.assertEqual(gateway.resolved, [])

    def test_workspace_without_core_is_silent(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/zeus-writer"],
            },
            gateway,
        )
        self.assertEqual(output, {})
        self.assertEqual(gateway.resolved, [])

    def test_index_generation_mismatch_fails_closed(self):
        class MismatchGateway(FakeGateway):
            def resolve(self, project):
                result = super().resolve(project)
                result["continuation"]["canonical_ir"]["index_id"] = "idx-other"
                return result

        with self.assertRaisesRegex(ValueError, "index generation mismatch"):
            build_injection(
                {
                    "invocationNum": 0,
                    "workspacePaths": ["/home/ubuntu/agentmanager"],
                },
                MismatchGateway(),
            )


if __name__ == "__main__":
    unittest.main()
