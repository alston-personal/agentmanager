import unittest

from agent_core.gaia_intake import Asset, Disposition, Proposal
from agent_core.gaia_project_adapter import LocalProjectEvidence
from agent_core.gaia_directory_adapter import DirectoryEvidence
from agent_core.gaia_reconcile import reconcile_project_proposal


def local(*assets):
    return LocalProjectEvidence(tuple(assets), "/project-store", ())


def directory(*assets):
    return DirectoryEvidence(tuple(assets), "/governance-directory", ())


class GaiaReconcileTest(unittest.TestCase):
    def test_confirmed_parent_routes_to_existing_project(self):
        asset = Asset("project://mobile-node", "project", aliases=("Mobile Node",))
        proposal = Proposal("Personal Device Secretary", "project",
                            related_asset_ids=("project://mobile-node",))
        d = reconcile_project_proposal(proposal, local(asset), directory(asset))
        self.assertEqual(d.disposition, Disposition.EXTEND_PROJECT)
        self.assertEqual(d.canonical_parent, "project://mobile-node")
        self.assertTrue(d.requires_authorization)

    def test_source_conflict_blocks(self):
        a = Asset("project://mobile-node", "project", aliases=("Mobile Node",))
        b = Asset("project://alternate-node", "project", aliases=("Mobile Node",))
        proposal = Proposal("Mobile Node", "project")
        d = reconcile_project_proposal(proposal, local(a), directory(b))
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)

    def test_single_source_match_is_not_enough(self):
        a = Asset("project://mobile-node", "project", aliases=("Mobile Node",))
        proposal = Proposal("Mobile Node", "project")
        d = reconcile_project_proposal(proposal, local(a), directory())
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)

    def test_absence_is_not_global_uniqueness(self):
        d = reconcile_project_proposal(Proposal("New idea", "project"),
                                       local(), directory())
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)

    def test_new_trust_boundary_requires_approval(self):
        d = reconcile_project_proposal(
            Proposal("New sensitive project", "project", requests_new_trust_boundary=True),
            local(), directory())
        self.assertEqual(d.disposition, Disposition.NEEDS_HUMAN_APPROVAL)

    def test_unreadable_source_blocks(self):
        d = reconcile_project_proposal(
            Proposal("New idea", "project"),
            LocalProjectEvidence((), "/project-store", ("read_error",)),
            directory())
        self.assertEqual(d.disposition, Disposition.NEEDS_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
