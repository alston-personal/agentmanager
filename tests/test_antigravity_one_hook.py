from __future__ import annotations

import json
import unittest

from agentos_node.antigravity_one_hook import build_injection


class FakeGateway:
    def __init__(self):
        self.resolved = []

    def status(self):
        return {
            "schema": "agentos.one-mcp-status/v0.1",
            "connected": True,
            "realm_id": "realm-test",
            "node_id": "oracle-core-node",
        }

    def resolve(self, project):
        self.resolved.append(project)
        if project == "unrelated":
            raise KeyError(project)
        return {
            "schema": "agentos.resolve/v1",
            "project": {"id": project, "name": project},
            "project_resolution": {
                "resolved": {
                    "project_id": project,
                    "repo": f"example/{project}",
                    "branch": "core/integration",
                    "canonical_path": f"/home/ubuntu/{project}",
                    "node": "oracle-core-node",
                }
            },
            "mutation_allowed": False,
            "active_goal": "continue canonical work",
            "next_action": "run next verified step",
            "availability": {"continuation": True},
            "provenance": {"continuation": "project/continuity/latest.json"},
        }


class AntigravityOneHookTests(unittest.TestCase):
    def test_first_invocation_injects_one_hydration(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/home/ubuntu/agentmanager"],
                "modelName": "gemini-test",
            },
            gateway,
        )
        self.assertIn("injectSteps", output)
        message = output["injectSteps"][0]["ephemeralMessage"]
        self.assertIn("ONE_PREINVOCATION_HOOK", message)
        self.assertIn("realm-test", message)
        self.assertIn("continue canonical work", message)
        self.assertNotIn("token", message.casefold())
        self.assertEqual(gateway.resolved, ["agentmanager"])

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

    def test_unrelated_workspace_is_silent(self):
        gateway = FakeGateway()
        output = build_injection(
            {
                "invocationNum": 0,
                "workspacePaths": ["/tmp/unrelated"],
            },
            gateway,
        )
        self.assertEqual(output, {})


if __name__ == "__main__":
    unittest.main()
