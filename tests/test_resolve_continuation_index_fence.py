import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_core.resolve_facade import resolve_continuation


class ResolveContinuationIndexFenceTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name) / "data"
        self.project_dir = self.root / "projects" / "agentos-core"
        (self.project_dir / "continuity").mkdir(parents=True)
        self.project = {
            "id": "agentos-core",
            "name": "AgentOS Core",
            "aliases": ["AgentOS"],
            "identity_source": "governance-directory",
            "governance_entity_id": "project://agentos-core",
            "integrity": {"complete": True, "mutation_allowed": True},
            "resolution_receipt": {"schema": "agentos.project-resolution/v1"},
        }

    def tearDown(self):
        self.td.cleanup()

    def _write(self, head_index, continuation_index):
        head = {
            "schema": "agentos.execution-head/v1",
            "index_id": head_index,
            "active_goal": "Continue AgentOS Core",
        }
        continuation = {
            "protocol": "ANCP/1.0",
            "index_id": continuation_index,
            "recommended_action": "Run fresh-chat acceptance",
            "canonical_ir": {
                "schema_version": "agentos.ir/v1",
                "index_id": continuation_index,
                "ir_id": "ir-live",
                "goal": "Continue AgentOS Core",
                "constraints": [],
                "decisions": [],
                "pending_tasks": [],
                "continuation": {"recommended_action": "Run fresh-chat acceptance"},
            },
        }
        (self.project_dir / "execution-head.json").write_text(json.dumps(head), encoding="utf-8")
        (self.project_dir / "continuity" / "latest.json").write_text(json.dumps(continuation), encoding="utf-8")

    @patch("agent_core.resolve_facade.resolve_project_identity")
    def test_accepts_matching_index_generation(self, resolve):
        resolve.return_value = self.project
        self._write("idx-7", "idx-7")
        result = resolve_continuation("agentos-core", data_root=self.root)
        self.assertTrue(result["availability"]["execution_head"])
        self.assertTrue(result["availability"]["continuation"])
        self.assertEqual(result["execution_head"]["index_id"], "idx-7")
        self.assertEqual(result["continuation"]["goal"], "Continue AgentOS Core")
        self.assertEqual(result["next_action"], "Run fresh-chat acceptance")

    @patch("agent_core.resolve_facade.resolve_project_identity")
    def test_rejects_mixed_index_generation(self, resolve):
        resolve.return_value = self.project
        self._write("idx-new", "idx-old")
        with self.assertRaisesRegex(ValueError, "continuation index generation mismatch"):
            resolve_continuation("agentos-core", data_root=self.root)

    @patch("agent_core.resolve_facade.resolve_project_identity")
    def test_rejects_half_published_indexed_state(self, resolve):
        resolve.return_value = self.project
        head = {"schema": "agentos.execution-head/v1", "index_id": "idx-new"}
        (self.project_dir / "execution-head.json").write_text(json.dumps(head), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "continuation index generation mismatch"):
            resolve_continuation("agentos-core", data_root=self.root)


if __name__ == "__main__":
    unittest.main()
