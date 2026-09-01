import unittest

from agent_core.transport_routing import (
    TransportUnavailable,
    UnauthorizedTransport,
    UnknownIntentClass,
    resolve_transport,
)


class TransportRoutingTests(unittest.TestCase):
    def test_control_plane_prefers_direct_one(self):
        decision = resolve_transport(
            "control_plane",
            {"one_direct", "agentos_mcp_app", "control_inbox", "github_actions"},
        )
        self.assertEqual(decision.transport, "one_direct")

    def test_control_plane_uses_mcp_before_control_inbox(self):
        decision = resolve_transport(
            "control_plane",
            {"agentos_mcp_app", "control_inbox", "github_actions"},
        )
        self.assertEqual(decision.transport, "agentos_mcp_app")

    def test_current_chatgpt_bootstrap_uses_control_inbox(self):
        decision = resolve_transport(
            "control_plane",
            {"control_inbox", "github_actions"},
        )
        self.assertEqual(decision.transport, "control_inbox")

    def test_control_plane_never_falls_back_to_github_actions(self):
        with self.assertRaises(TransportUnavailable):
            resolve_transport("control_plane", {"github_actions"})

    def test_explicit_github_actions_is_rejected_for_control_plane(self):
        with self.assertRaises(UnauthorizedTransport):
            resolve_transport(
                "control_plane",
                {"control_inbox", "github_actions"},
                requested_transport="github_actions",
            )

    def test_transport_failure_does_not_expand_authority(self):
        # The caller reports the ONE-side transports unavailable after a failure.
        # Reachable Actions must still not become authorized as a side effect.
        with self.assertRaises(TransportUnavailable):
            resolve_transport(
                "control_plane",
                {
                    "one_direct": False,
                    "agentos_mcp_app": False,
                    "control_inbox": False,
                    "github_actions": True,
                },
            )

    def test_explicit_workflow_routes_to_github_actions(self):
        decision = resolve_transport("workflow", {"github_actions"})
        self.assertEqual(decision.transport, "github_actions")

    def test_workflow_cannot_borrow_control_transport(self):
        with self.assertRaises(TransportUnavailable):
            resolve_transport("workflow", {"control_inbox"})

    def test_same_snapshot_is_deterministic(self):
        available = {"control_inbox", "github_actions"}
        first = resolve_transport("control_plane", available)
        second = resolve_transport("control_plane", reversed(tuple(available)))
        self.assertEqual(first, second)
        self.assertEqual(first.transport, "control_inbox")

    def test_unknown_intent_fails_closed(self):
        with self.assertRaises(UnknownIntentClass):
            resolve_transport("whatever_is_convenient", {"github_actions"})


if __name__ == "__main__":
    unittest.main()
