from __future__ import annotations

import json
import unittest

from agentos_node.antigravity_one_hook import build_injection, _safe_failure_code
from agentos_node.one_mcp import OneGatewayError


class FakeGateway:
    def __init__(self, *, index_id="idx-7", ir_id="ir-core-152"):
        self.resolved = []
        self.index_id = index_id
        self.ir_id = ir_id

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
                    "ir_id": self.ir_id,
                    "parent_ir_id": "ir-core-151",
                    "goal": "Complete #152 Antigravity IR hydration",
                    "constraints": ["Workspace is not continuation authority"],
                    "decisions": ["Canonical IR is the durable continuation state"],
                    "pending_tasks": ["Run fresh Codex regression"],
                    "continuation": {"recommended_action": "Run fresh Codex regression"},
                    "capability": "agentos.one.resolve",
                }
            },
            "next_action": "Run fresh Codex regression",
            "provenance": {"continuation": "project/continuity/latest.json"},
        }

    def resolve_active(self):
        result = self.resolve("agentos-core")
        result["selection_source"] = "ONE_ACTIVE_CONTINUATION"
        result["active_selector"] = selector(self.index_id, self.ir_id)
        return result


def selector(index_id="idx-7", ir_id="ir-core-152"):
    return {
        "schema": "agentos.active-continuation/v1",
        "project_id": "agentos-core",
        "index_id": index_id,
        "ir_id": ir_id,
    }


def envelope_from(output):
    message = output["injectSteps"][0]["ephemeralMessage"]
    return json.loads(message.split("\n", 1)[1])


class AntigravityOneHookTests(unittest.TestCase):
    def test_first_invocation_hydrates_active_canonical_ir(self):
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
            selector=selector(),
        )
        self.assertIn("injectSteps", output)
        message = output["injectSteps"][0]["ephemeralMessage"]
        self.assertIn("ONE_PREINVOCATION_IR", message)
        self.assertIn("ONE_ACTIVE_CONTINUATION", message)
        self.assertIn("ir-core-152", message)
        self.assertIn("idx-7", message)
        self.assertNotIn("zeus-writer", message)
        self.assertNotIn("privacy-guard", message)
        self.assertNotIn("token", message.casefold())
        self.assertEqual(gateway.resolved, ["agentos-core"])
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-gemini")
        self.assertTrue(envelope["executor_identity_bound"])
        self.assertEqual(envelope["selection_source"], "ONE_ACTIVE_CONTINUATION")

    def test_hook_resolves_active_selector_when_not_injected_by_caller(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["C:/unrelated/workspace"],
                "modelName": "gemini-test",
            },
            gateway,
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["active_selector"]["ir_id"], "ir-core-152")
        self.assertEqual(envelope["canonical_ir"]["project_id"], "agentos-core")
        self.assertEqual(gateway.resolved, ["agentos-core"])
        self.assertNotIn("unrelated", json.dumps(envelope))

    def test_acas_workspace_cannot_override_active_core_ir(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/acas"],
                "modelName": "gpt-5-codex",
            },
            gateway,
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["canonical_ir"]["project_id"], "agentos-core")
        self.assertEqual(envelope["executor_class"], "antigravity-codex")
        self.assertEqual(gateway.resolved, ["agentos-core"])
        self.assertNotIn("/home/ubuntu/acas", json.dumps(envelope))

    def test_nested_workspace_cannot_override_active_core_ir(self):
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/agentmanager/workspace/if-tv-station"],
                "modelName": "gpt-5-codex",
            },
            FakeGateway(),
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["canonical_ir"]["project_id"], "agentos-core")
        self.assertNotIn("if-tv-station", json.dumps(envelope))

    def test_empty_workspace_still_hydrates_active_ir(self):
        output = build_injection(
            {"invocationNum": 0, "workspacePaths": [], "modelName": "gpt-5-codex"},
            FakeGateway(),
            selector=selector(),
        )
        self.assertEqual(envelope_from(output)["canonical_ir"]["project_id"], "agentos-core")

    def test_codex_model_binds_codex_executor(self):
        output = build_injection(
            {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"], "modelName": "gpt-5-codex"},
            FakeGateway(),
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-codex")
        self.assertTrue(envelope["executor_identity_bound"])
        self.assertEqual(envelope["model_name"], "gpt-5-codex")

    def test_unknown_model_does_not_guess_executor_identity(self):
        output = build_injection(
            {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"], "modelName": "mystery-model"},
            FakeGateway(),
            selector=selector(),
        )
        envelope = envelope_from(output)
        self.assertEqual(envelope["executor_class"], "antigravity-unknown")
        self.assertFalse(envelope["executor_identity_bound"])

    def test_later_invocation_is_silent(self):
        gateway = FakeGateway()
        output = build_injection(
            {"invocationNum": 1, "workspacePaths": ["/home/ubuntu/acas"]},
            gateway,
            selector=selector(),
        )
        self.assertEqual(output, {})
        self.assertEqual(gateway.resolved, [])

    def test_stale_active_selector_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "active continuation selector is stale"):
            build_injection(
                {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"]},
                FakeGateway(),
                selector=selector(index_id="idx-stale"),
            )

    def test_index_generation_mismatch_fails_closed(self):
        class MismatchGateway(FakeGateway):
            def resolve(self, project):
                result = super().resolve(project)
                result["continuation"]["canonical_ir"]["index_id"] = "idx-other"
                return result

        with self.assertRaisesRegex(ValueError, "index generation mismatch"):
            build_injection(
                {"invocationNum": 0, "workspacePaths": ["/home/ubuntu/acas"]},
                MismatchGateway(),
                selector=selector(),
            )

    def test_failure_codes_do_not_echo_exception_details(self):
        secret_error = RuntimeError("Bearer TOPSECRET /home/private/session")
        code = _safe_failure_code(secret_error)
        self.assertEqual(code, "one_hydration_runtime_failed")
        self.assertNotIn("TOPSECRET", code)
        self.assertNotIn("/home/private", code)

        one_error = OneGatewayError("one_http_503")
        self.assertEqual(_safe_failure_code(one_error), "one_http_503")


if __name__ == "__main__":
    unittest.main()
