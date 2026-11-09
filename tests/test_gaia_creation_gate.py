import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent_core import project_store
from agent_core.gaia_creation_gate import (
    CreationAuthorization, CreationDenied, register_reviewed_project,
)
from agent_core.gaia_decision_record import issue_review_record
from agent_core.gaia_intake import Decision, Disposition, Proposal
from agent_core.project_store import CanonicalProjectRegistration, ProjectSourceAuthority


class GaiaCreationGateTest(unittest.TestCase):
    def setUp(self):
        self.project = CanonicalProjectRegistration(
            project_id="new-service", display_name="New Service",
            source=ProjectSourceAuthority(
                repo="alston-personal/agentmanager", branch="main",
                canonical_path="/tmp/source", node="oracle-node"),
            state_document="STATUS.md")
        self.record = issue_review_record(
            Proposal("New Service", "project"),
            Decision(Disposition.NEEDS_HUMAN_APPROVAL, None, ("not_found",)),
            source_refs=("atlas://snapshot/abc",),
            reviewed_at="2026-11-09T00:00:00+00:00")
        self.authorization = CreationAuthorization(
            decision_hash=self.record.content_hash,
            project_id="new-service", actor_id="role://governance.keeper",
            approval_id="one://approval/123",
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())

    def run_registration(self, authorization=None, record=None, verified=False):
        with patch.object(project_store.config, "PROJECTS_DIR", Path("/nonexistent")):
            with patch("agent_core.gaia_creation_gate.register_canonical_project") as write:
                write.return_value = {"project_id": "new-service"}
                result = None
                try:
                    result = register_reviewed_project(
                        self.project, record or self.record, authorization or self.authorization,
                        verify_authorization=lambda _: verified)
                except CreationDenied:
                    self.assert_not_written(write)
                    raise
                write.assert_called_once()
                return result

    def assert_not_written(self, mock):
        mock.assert_not_called()

    def test_rejects_unverified_authority(self):
        with self.assertRaisesRegex(CreationDenied, "approval_not_verified"):
            self.run_registration()

    def test_independent_verified_authority_allows_scoped_write(self):
        self.assertEqual(self.run_registration(verified=True)["project_id"], "new-service")

    def test_rejects_other_project_scope(self):
        with self.assertRaisesRegex(CreationDenied, "project_scope_mismatch"):
            self.run_registration(replace(self.authorization, project_id="other"), verified=True)

    def test_rejects_expired_approval(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        with self.assertRaisesRegex(CreationDenied, "approval_expired"):
            self.run_registration(replace(self.authorization, expires_at=past), verified=True)

    def test_rejects_tampered_review(self):
        with self.assertRaisesRegex(CreationDenied, "invalid_review_record"):
            self.run_registration(record=replace(self.record, reviewed_at="2027-01-01T00:00:00+00:00"), verified=True)

    def test_existing_parent_is_not_new_project(self):
        rec = issue_review_record(
            Proposal("Extension", "project"),
            Decision(Disposition.EXTEND_PROJECT, "project://mobile-node", ("existing",)),
            source_refs=("project://mobile-node",),
            reviewed_at="2026-11-09T00:00:00+00:00")
        with self.assertRaisesRegex(CreationDenied, "review_is_not_new_project_proposal"):
            self.run_registration(record=rec, verified=True)


if __name__ == "__main__":
    unittest.main()
