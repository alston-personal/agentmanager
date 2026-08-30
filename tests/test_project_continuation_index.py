import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_core.project_continuation_index import publish_project_continuation, validate_publish_params


class ProjectContinuationIndexTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "data"
        (self.root / "projects" / "agentos-core").mkdir(parents=True)
        self.params = {
            "project_id": "agentos-core",
            "execution_head": {
                "schema": "agentos.execution-head/v1",
                "index_id": "idx-1",
                "active_goal": "Finish canonical continuation indexing",
                "execution_head": {"status": "in_progress"},
            },
            "continuation": {
                "protocol": "ANCP/1.0",
                "index_id": "idx-1",
                "recommended_action": "Re-run authenticated resolve",
                "canonical_ir": {
                    "schema_version": "agentos.ir/v1",
                    "index_id": "idx-1",
                    "ir_id": "ir-1",
                    "parent_ir_id": None,
                    "goal": "Finish canonical continuation indexing",
                    "constraints": ["Do not infer identity from Git"],
                    "decisions": [],
                    "pending_tasks": ["Re-run authenticated resolve"],
                    "continuation": {"recommended_action": "Re-run authenticated resolve"},
                    "capability": "agentos.one.resolve",
                },
            },
        }
        self.project = {
            "id": "agentos-core",
            "identity_source": "governance-directory",
            "governance_entity_id": "project://agentos-core",
            "integrity": {"mutation_allowed": True},
        }

    def tearDown(self):
        self.td.cleanup()

    def test_rejects_noncanonical_project(self):
        params = dict(self.params)
        params["project_id"] = "other"
        with self.assertRaisesRegex(ValueError, "restricted to agentos-core"):
            validate_publish_params(params)

    def test_rejects_mismatched_index_generation(self):
        params = json.loads(json.dumps(self.params))
        params["continuation"]["canonical_ir"]["index_id"] = "idx-2"
        with self.assertRaisesRegex(ValueError, "index_id mismatch"):
            validate_publish_params(params)

    def test_rejects_wrong_ir_schema(self):
        params = json.loads(json.dumps(self.params))
        params["continuation"]["canonical_ir"]["schema_version"] = "other/v1"
        with self.assertRaisesRegex(ValueError, "agentos.ir/v1"):
            validate_publish_params(params)

    @patch("agent_core.project_continuation_index.resolve_project_identity")
    def test_publishes_same_index_to_both_canonical_paths(self, resolve):
        resolve.return_value = self.project
        receipt = publish_project_continuation(self.params, data_root=self.root)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["index_id"], "idx-1")
        head = json.loads((self.root / "projects" / "agentos-core" / "execution-head.json").read_text())
        cont = json.loads((self.root / "projects" / "agentos-core" / "continuity" / "latest.json").read_text())
        self.assertEqual(head["index_id"], cont["index_id"])
        self.assertEqual(cont["canonical_ir"]["schema_version"], "agentos.ir/v1")
        self.assertTrue(receipt["execution_head"]["sha256"].startswith("sha256:"))
        self.assertTrue(receipt["continuation"]["sha256"].startswith("sha256:"))

    @patch("agent_core.project_continuation_index.resolve_project_identity")
    def test_rejects_governance_identity_without_mutation_authority(self, resolve):
        project = dict(self.project)
        project["integrity"] = {"mutation_allowed": False}
        resolve.return_value = project
        with self.assertRaisesRegex(ValueError, "does not permit mutation"):
            publish_project_continuation(self.params, data_root=self.root)

    @patch("agent_core.project_continuation_index.resolve_project_identity")
    def test_rejects_symlink_project_directory(self, resolve):
        resolve.return_value = self.project
        project_dir = self.root / "projects" / "agentos-core"
        project_dir.rmdir()
        outside = Path(self.td.name) / "outside"
        outside.mkdir()
        project_dir.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            publish_project_continuation(self.params, data_root=self.root)


if __name__ == "__main__":
    unittest.main()
