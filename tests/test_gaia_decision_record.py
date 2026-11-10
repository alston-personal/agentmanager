import unittest
from dataclasses import replace

from agent_core.gaia_intake import Decision, Disposition, Proposal
from agent_core.gaia_decision_record import issue_review_record, verify_review_record


class GaiaReviewRecordTests(unittest.TestCase):
    def setUp(self):
        self.proposal = Proposal(
            title="Personal Device Secretary", kind="project",
            related_asset_ids=("project://mobile-node",))
        self.decision = Decision(
            Disposition.EXTEND_PROJECT,
            "project://mobile-node",
            ("local_project_store:/data/projects",
             "governance_projection:/data/governance/directory.json"),
        )

    def issue(self):
        return issue_review_record(
            self.proposal, self.decision,
            source_refs=("project://mobile-node@sha256:abc",),
            reviewed_at="2026-11-09T13:30:00+08:00")

    def test_review_is_content_addressed_but_has_no_authority(self):
        record = self.issue()
        self.assertTrue(verify_review_record(record))
        self.assertEqual(record.authority, "none")
        self.assertTrue(record.decision["requires_authorization"])
        self.assertEqual(record, self.issue())

    def test_modified_decision_or_sources_fail_integrity(self):
        record = self.issue()
        self.assertFalse(verify_review_record(replace(
            record, decision={**record.decision, "canonical_parent": "project://other"})))
        self.assertFalse(verify_review_record(replace(
            record, source_refs=("project://unknown",))))
        self.assertFalse(verify_review_record(replace(record, authority="approved")))

    def test_requires_source_provenance_and_aware_time(self):
        with self.assertRaises(ValueError):
            issue_review_record(self.proposal, self.decision,
                                source_refs=(), reviewed_at="2026-11-09T13:30:00+08:00")
        with self.assertRaises(ValueError):
            issue_review_record(self.proposal, self.decision,
                                source_refs=("source",), reviewed_at="2026-11-09T13:30:00")

    def test_approval_disposition_is_not_informational_authorization(self):
        d = Decision(Disposition.NEEDS_HUMAN_APPROVAL, None,
                     ("no_existing_asset",))
        record = issue_review_record(self.proposal, d,
                     source_refs=("issue://420",),
                     reviewed_at="2026-11-09T05:30:00Z")
        self.assertTrue(verify_review_record(record))
        self.assertEqual(record.authority, "none")


if __name__ == "__main__":
    unittest.main()
