import json
import tempfile
import unittest
from pathlib import Path

from agent_core.gaia_directory_adapter import (
    read_governance_directory, review_directory_candidate,
)
from agent_core.gaia_intake import Disposition, Proposal


class GaiaDirectoryAdapterTest(unittest.TestCase):
    def test_positive_existing_project_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directory.json"
            path.write_text(json.dumps({
                "updated_at": "2026-11-09T00:00:00+00:00",
                "entities": {"project://mobile-node": {
                    "id": "project://mobile-node", "kind": "project",
                    "name": "Mobile Node", "state": "implemented",
                    "provides": [], "metadata": {"aliases": ["Phone Node"]},
                }},
            }), encoding="utf-8")
            snapshot = read_governance_directory(path)
            d = review_directory_candidate(
                Proposal("Personal Secretary", "project",
                         related_asset_ids=("project://mobile-node",)), snapshot)
            self.assertEqual(d.disposition, Disposition.EXTEND_PROJECT)
            self.assertTrue(d.requires_authorization)
            self.assertIn("governance_projection:", d.evidence[0])

    def test_missing_directory_does_not_approve_new_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = read_governance_directory(Path(tmp) / "not-exists")
        self.assertEqual(snapshot.errors, ("directory_missing",))

    def test_unknown_project_cannot_be_declared_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directory.json"
            path.write_text(json.dumps({"updated_at":"2026-11-09","entities":{}}))
            result = review_directory_candidate(
                Proposal("New Project", "project"), read_governance_directory(path))
            self.assertEqual(result.disposition, Disposition.NEEDS_EVIDENCE)

    def test_rejects_corrupted_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directory.json"
            path.write_text(json.dumps({"updated_at":"2026-11-09",
                "entities":{"project://a":{"id":"project://b","kind":"project"}}}))
            self.assertIn("directory_identity_mismatch", read_governance_directory(path).errors)

    def test_rejects_unattested_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "directory.json"
            path.write_text(json.dumps({"entities":{}}))
            self.assertIn("directory_not_attested", read_governance_directory(path).errors)


if __name__ == "__main__":
    unittest.main()
