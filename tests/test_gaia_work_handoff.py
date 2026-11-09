import tempfile
import unittest
from pathlib import Path

from agent_core.gaia_intake import Decision, Disposition, Proposal
from agent_core.gaia_decision_record import issue_review_record
from agent_core.gaia_work_handoff import (
    GaiaHandoffDenied, propose_existing_project_work, admit_existing_project_work,
)
from scripts.work_completion import load


def review(disposition=Disposition.EXTEND_PROJECT):
    return issue_review_record(
        Proposal("Personal Device Secretary", "project",
                 related_asset_ids=("project://mobile-node",)),
        Decision(disposition, "project://mobile-node" if disposition == Disposition.EXTEND_PROJECT else None,
                 ("verified_project_match",)),
        source_refs=("project://mobile-node@sha256:test",),
        reviewed_at="2026-11-09T06:00:00+00:00")


class GaiaHandoffTest(unittest.TestCase):
    def envelope(self):
        return propose_existing_project_work(
            review(), source_issue_url="https://github.com/alston-personal/agentmanager/issues/2156",
            workspace="/tmp/agentos-gaia")

    def test_existing_mobile_task_is_typed_and_deterministic(self):
        envelope = self.envelope()
        self.assertEqual(envelope, self.envelope())
        self.assertEqual(envelope["schema"], "agentos.work-intake/v1")
        self.assertEqual(envelope["project_id"], "mobile-node")
        self.assertNotIn("owner", envelope)
        self.assertNotIn("executor", envelope)

    def test_new_project_must_not_be_dispatched(self):
        with self.assertRaises(GaiaHandoffDenied):
            propose_existing_project_work(
                review(Disposition.NEEDS_HUMAN_APPROVAL),
                source_issue_url="https://github.com/alston-personal/agentmanager/issues/2156",
                workspace="/tmp/agentos-gaia")

    def test_untrusted_handoff_cannot_mutate(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "work-items.json"
            with self.assertRaisesRegex(GaiaHandoffDenied, "intake_not_authorized"):
                admit_existing_project_work(state, review(), self.envelope(),
                                             verify_intake_authority=lambda _: False)
            self.assertFalse(state.exists())

    def test_authorized_work_goes_to_existing_completion_controller_once(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "work-items.json"
            envelope = self.envelope()
            one = admit_existing_project_work(state, review(), envelope,
                                               verify_intake_authority=lambda _: True)
            two = admit_existing_project_work(state, review(), envelope,
                                               verify_intake_authority=lambda _: True)
            self.assertEqual(one["work_id"], two["work_id"])
            self.assertEqual(one["owner"], "role://completion.controller")
            self.assertEqual(len(load(state)["items"]), 1)

    def test_admission_rejects_mutated_owner_and_action(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "work-items.json"
            envelope = self.envelope()
            for change in ({"project_id": "other"},
                           {"next_action": "execute arbitrary command"},
                           {"owner": "role://untrusted"},
                           {"acceptance": ["fake"]}):
                with self.subTest(change=change):
                    changed = {**envelope, **change}
                    with self.assertRaisesRegex(GaiaHandoffDenied, "intake_envelope_mismatch"):
                        admit_existing_project_work(
                            state, review(), changed,
                            verify_intake_authority=lambda _: True)
            self.assertFalse(state.exists())

    def test_admission_rejects_inconsistent_review(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "work-items.json"
            with self.assertRaises(GaiaHandoffDenied):
                admit_existing_project_work(
                    state, review(Disposition.NEEDS_HUMAN_APPROVAL), self.envelope(),
                    verify_intake_authority=lambda _: True)
            self.assertFalse(state.exists())

    def test_invalid_issue_or_relative_workspace_rejected(self):
        with self.assertRaises(GaiaHandoffDenied):
            propose_existing_project_work(review(), source_issue_url="https://invalid.test/issue",
                                           workspace="/tmp/agentos")
        with self.assertRaises(GaiaHandoffDenied):
            propose_existing_project_work(review(), source_issue_url="https://github.com/alston-personal/agentmanager/issues/2156",
                                           workspace="relative")


if __name__ == "__main__":
    unittest.main()
