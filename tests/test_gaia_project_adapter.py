import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from agent_core.gaia_intake import Disposition, Proposal
from agent_core.gaia_project_adapter import (
    LocalProjectEvidence, read_local_projects, review_existing_local_project,
)


class GaiaProjectAdapterTest(unittest.TestCase):
    def test_reads_existing_project_with_provenance(self):
        p = SimpleNamespace(project_id="mobile-node", display_name="Mobile Node",
                            capabilities_provided=["mobile.enroll"])
        with patch("agent_core.config.PROJECTS_DIR", Path("/tmp/missing-agentos-projects")):
            snapshot = read_local_projects()
            self.assertIn("project_store_missing", snapshot.errors)
        with patch("agent_core.config.PROJECTS_DIR") as root, \
             patch("agent_core.project_store.list_projects", return_value=[p]):
            root.is_dir.return_value = True
            root.iterdir.return_value = [SimpleNamespace(is_dir=lambda: True)]
            root.__str__ = lambda self: "/sandbox/projects"
            snapshot = read_local_projects()
        self.assertEqual(len(snapshot.assets), 1)
        self.assertEqual(snapshot.assets[0].canonical_id, "project://mobile-node")
        self.assertFalse(snapshot.errors)

    def test_links_known_parent_but_never_creates_it(self):
        from agent_core.gaia_intake import Asset
        evidence = LocalProjectEvidence((Asset("project://mobile-node", "project",
                                              aliases=("Mobile Node",)),),
                                        "/agent-data/projects", ())
        decision = review_existing_local_project(
            Proposal("Phone secretary", "project",
                     related_asset_ids=("project://mobile-node",)), evidence)
        self.assertEqual(decision.disposition, Disposition.EXTEND_PROJECT)
        self.assertTrue(decision.requires_authorization)

    def test_unknown_remains_evidence_needed_not_approved_creation(self):
        evidence = LocalProjectEvidence((), "/agent-data/projects", ())
        decision = review_existing_local_project(
            Proposal("New application", "project"), evidence)
        self.assertEqual(decision.disposition, Disposition.NEEDS_EVIDENCE)
        self.assertIn("global_registry_not_checked", decision.evidence)

    def test_missing_store_fails_closed(self):
        evidence = LocalProjectEvidence((), "", ("project_store_missing",))
        decision = review_existing_local_project(Proposal("Phone", "project"), evidence)
        self.assertEqual(decision.disposition, Disposition.NEEDS_EVIDENCE)

    def test_new_trust_boundary_needs_human(self):
        evidence = LocalProjectEvidence((), "/agent-data/projects", ())
        decision = review_existing_local_project(
            Proposal("Sensitive client", "project", requests_new_trust_boundary=True), evidence)
        self.assertEqual(decision.disposition, Disposition.NEEDS_HUMAN_APPROVAL)


if __name__ == "__main__":
    unittest.main()
