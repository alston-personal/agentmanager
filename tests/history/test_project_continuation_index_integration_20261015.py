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

    def _child_params(self):
        params = json.loads(json.dumps(self.params))
        params["execution_head"]["index_id"] = "idx-2"
        params["execution_head"]["active_goal"] = "Run E3"
        params["continuation"]["index_id"] = "idx-2"
        params["continuation"]["recommended_action"] = "Open fresh Codex"
        ir = params["continuation"]["canonical_ir"]
        ir["index_id"] = "idx-2"
        ir["ir_id"] = "ir-2"
        ir["parent_ir_id"] = "ir-1"
        ir["goal"] = "Run E3"
        ir["continuation"] = {"recommended_action": "Open fresh Codex"}
        return params

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
    def test_guarded_advance_requires_exact_current_parent(self, resolve):
        resolve.return_value = self.project
        publish_project_continuation(self.params, data_root=self.root)
        receipt = publish_project_continuation(
            self._child_params(),
            data_root=self.root,
            expected_index_id="idx-1",
            expected_ir_id="ir-1",
        )
        self.assertTrue(receipt["guarded_advance"])
        self.assertEqual(receipt["parent_ir_id"], "ir-1")
        self.assertEqual(receipt["index_id"], "idx-2")
        self.assertEqual(receipt["ir_id"], "ir-2")

    @patch("agent_core.project_continuation_index.resolve_project_identity")
    def test_guarded_advance_rejects_stale_parent_without_mutation(self, resolve):
        resolve.return_value = self.project
        publish_project_continuation(self.params, data_root=self.root)
        before_head = (self.root / "projects" / "agentos-core" / "execution-head.json").read_bytes()
        before_cont = (self.root / "projects" / "agentos-core" / "continuity" / "latest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "stale canonical IR parent"):
            publish_project_continuation(
                self._child_params(),
                data_root=self.root,
                expected_index_id="idx-stale",
                expected_ir_id="ir-stale",
            )
        self.assertEqual(before_head, (self.root / "projects" / "agentos-core" / "execution-head.json").read_bytes())
        self.assertEqual(before_cont, (self.root / "projects" / "agentos-core" / "continuity" / "latest.json").read_bytes())

    @patch("agent_core.project_continuation_index.resolve_project_identity")
    def test_guarded_advance_rejects_wrong_parent_ir_before_mutation(self, resolve):
        resolve.return_value = self.project
        publish_project_continuation(self.params, data_root=self.root)
        child = self._child_params()
        child["continuation"]["canonical_ir"]["parent_ir_id"] = "ir-other"
        with self.assertRaisesRegex(ValueError, "parent_ir_id"):
            publish_project_continuation(
                child,
                data_root=self.root,
                expected_index_id="idx-1",
                expected_ir_id="ir-1",
            )

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
