"""Decision-only synchronization policy: never silently mutate branches."""
import unittest

from scripts.branch_sync_policy import assess_sync_point


BASE = dict(
    kind="code", mainline_current=False, checkpoint_saved=True,
    lease_fenced=True, worktree_clean=True, overlapping_changes="none",
    governance_or_security_change=False, hours_since_main_sync=1,
)


def decide(**overrides):
    return assess_sync_point(**{**BASE, **overrides})


class BranchSyncPolicyTests(unittest.TestCase):
    def test_fresh_work_requires_no_integration(self):
        self.assertEqual(decide(mainline_current=True)["status"], "CURRENT")

    def test_unverified_main_fails_to_approve_sync(self):
        self.assertEqual(decide(mainline_current=None)["status"], "EVIDENCE_REQUIRED")

    def test_ordinary_independent_work_may_reach_safe_checkpoint(self):
        result = decide()
        self.assertEqual(result["status"], "SAFE_SYNC_CANDIDATE")
        self.assertFalse(result["auto_merge_authorized"])
        self.assertFalse(result["source_mutated"])
        self.assertFalse(result["receipt_verified"])

    def test_dirty_or_unfenced_state_cannot_merge(self):
        for field in ("checkpoint_saved", "lease_fenced", "worktree_clean"):
            with self.subTest(field=field):
                result = decide(**{field: False})
                self.assertEqual(result["status"], "WAIT_FOR_SAFE_CHECKPOINT")

    def test_overlap_and_security_change_require_reconciliation(self):
        for kwargs in ({"overlapping_changes": "shared"},
                       {"governance_or_security_change": True}):
            result = decide(**kwargs)
            self.assertEqual(result["status"], "RECONCILE_REQUIRED")
            self.assertTrue(result["block_relevant_writes"])

    def test_unknown_dependency_not_automatically_classified_safe(self):
        self.assertEqual(decide(overlapping_changes="unknown")["status"],
                         "REVIEW_DEPENDENCIES")

    def test_age_72_hours_escalates_even_without_overlap(self):
        self.assertEqual(decide(hours_since_main_sync=71)["status"],
                         "SAFE_SYNC_CANDIDATE")
        result = decide(hours_since_main_sync=72)
        self.assertEqual(result["status"], "ESCALATE_STALE_BRANCH")
        self.assertTrue(result["block_relevant_writes"])

    def test_read_only_discovers_stale_branch_without_mutation(self):
        result = decide(kind="read_only", checkpoint_saved=False)
        self.assertEqual(result["status"], "READ_ONLY_CONTINUE")
        self.assertFalse(result["auto_merge_authorized"])

    def test_invalid_observations_fail_closed(self):
        for kwargs in ({"overlapping_changes": "guess"},
                       {"hours_since_main_sync": -1},
                       {"hours_since_main_sync": True},
                       {"mainline_current": "false"},
                       {"lease_fenced": "yes"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                decide(**kwargs)


if __name__ == "__main__":
    unittest.main()
