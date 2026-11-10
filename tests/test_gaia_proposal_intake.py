import unittest
from unittest.mock import patch

from agent_core.gaia_intake import Asset
from agent_core.gaia_project_adapter import LocalProjectEvidence
from agent_core.gaia_directory_adapter import DirectoryEvidence
from agent_core.gaia_decision_record import ReviewRecord, verify_review_record
from scripts.gaia_proposal_intake import examine


MOBILE = Asset("project://mobile-node", "project", aliases=("Mobile Node",))


class GaiaProposalIntakeTest(unittest.TestCase):
    @patch("scripts.gaia_proposal_intake.read_governance_directory")
    @patch("scripts.gaia_proposal_intake.read_local_projects")
    def test_known_mobile_parent_reuses_existing_program(self, get_local, get_directory):
        get_local.return_value = LocalProjectEvidence((MOBILE,), "/existing/projects", ())
        get_directory.return_value = DirectoryEvidence((MOBILE,), "/existing/directory", ())
        result = examine({
            "title": "Personal Device Secretary",
            "kind": "project",
            "related_asset_ids": ["project://mobile-node"],
        })
        self.assertEqual(result["status"], "REVIEWED_INFORMATIONAL_ONLY")
        self.assertEqual(result["review"]["decision"]["disposition"], "EXTEND_PROJECT")
        self.assertEqual(result["review"]["decision"]["canonical_parent"], "project://mobile-node")
        self.assertEqual(result["next_step"], "route_to_existing_project_owner_for_scoped_work_intake")
        self.assertFalse(result["creation_authorized"])
        self.assertFalse(result["execution_authorized"])
        rec = ReviewRecord(**result["review"])
        self.assertTrue(verify_review_record(rec))

    @patch("scripts.gaia_proposal_intake.read_governance_directory")
    @patch("scripts.gaia_proposal_intake.read_local_projects")
    def test_unknown_project_cannot_be_auto_created(self, get_local, get_directory):
        get_local.return_value = LocalProjectEvidence((), "/existing/projects", ())
        get_directory.return_value = DirectoryEvidence((), "/existing/directory", ())
        result = examine({"title": "New Product", "kind": "project"})
        self.assertEqual(result["review"]["decision"]["disposition"], "NEEDS_EVIDENCE")
        self.assertEqual(result["next_step"], "verify_atlas_global_inventory_before_creation")
        self.assertFalse(result["creation_authorized"])

    @patch("scripts.gaia_proposal_intake.read_governance_directory")
    @patch("scripts.gaia_proposal_intake.read_local_projects")
    def test_missing_registry_fails_closed(self, get_local, get_directory):
        get_local.return_value = LocalProjectEvidence((), "/missing", ("project_store_missing",))
        get_directory.return_value = DirectoryEvidence((MOBILE,), "/existing/directory", ())
        result = examine({"title": "Mobile Node", "kind": "project"})
        self.assertEqual(result["review"]["decision"]["disposition"], "NEEDS_EVIDENCE")

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            examine({"title": "Hello", "kind": "project", "approved": True})

    def test_non_project_and_invalid_input_rejected(self):
        for bad in (
            {"title": "Any", "kind": "role"},
            {"title": "", "kind": "project"},
            {"title": "Any", "kind": "project", "related_asset_ids": "a"},
            {"title": "Any", "kind": "project", "requests_new_trust_boundary": "yes"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                examine(bad)


if __name__ == "__main__":
    unittest.main()
