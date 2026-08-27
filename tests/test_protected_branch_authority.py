import unittest

from scripts.protected_branch_authority import authorize, load_policy


class ProtectedBranchAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy()

    def test_agent_cannot_merge_main_without_explicit_human_approval(self):
        decision = authorize(
            branch="main",
            actor_kind="agent",
            explicit_human_approval=False,
            via_pull_request=True,
            policy=self.policy,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.state, "AWAITING_HUMAN_APPROVAL")

    def test_mergeable_pr_is_not_authority(self):
        decision = authorize(
            branch="main",
            actor_kind="agent",
            explicit_human_approval=False,
            via_pull_request=True,
            policy=self.policy,
        )
        self.assertIn("authority", decision.reason)

    def test_direct_push_to_main_is_denied(self):
        decision = authorize(
            branch="main",
            actor_kind="human",
            explicit_human_approval=True,
            via_pull_request=False,
            policy=self.policy,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.state, "DENY")

    def test_explicit_human_approval_allows_human_merge(self):
        decision = authorize(
            branch="main",
            actor_kind="human",
            explicit_human_approval=True,
            via_pull_request=True,
            policy=self.policy,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.state, "ALLOW")

    def test_agent_still_does_not_gain_autonomous_authority_from_approval_flag(self):
        decision = authorize(
            branch="main",
            actor_kind="agent",
            explicit_human_approval=True,
            via_pull_request=True,
            policy=self.policy,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.state, "AWAITING_HUMAN_APPROVAL")

    def test_feature_branch_is_not_blocked(self):
        decision = authorize(
            branch="feature/example",
            actor_kind="agent",
            explicit_human_approval=False,
            via_pull_request=False,
            policy=self.policy,
        )
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.protected)


if __name__ == "__main__":
    unittest.main()
