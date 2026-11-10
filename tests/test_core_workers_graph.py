from __future__ import annotations

import json
import unittest
from pathlib import Path


GRAPH_PATH = Path(__file__).resolve().parent.parent / "governance" / "core-workers.json"
ALLOWED_STATUSES = {"queued", "running", "blocked", "accepted"}


class CoreWorkersGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        cls.workers = {int(item["issue"]): item for item in cls.graph["workers"]}

    def test_graph_schema_and_issue_ids_are_unique(self):
        self.assertEqual(self.graph["schema"], "agentos.core-workers/v0")
        raw_ids = [int(item["issue"]) for item in self.graph["workers"]]
        self.assertEqual(len(raw_ids), len(set(raw_ids)))
        self.assertTrue(self.graph.get("generated_at"))
        self.assertTrue(all(item.get("status") in ALLOWED_STATUSES for item in self.graph["workers"]))

    def test_completed_employee_extraction_is_not_queued(self):
        worker = self.workers[151]
        self.assertEqual(worker["status"], "accepted")
        self.assertEqual(worker["blocking_scope"], [])
        self.assertIn("issue/151#issuecomment-5504064405", worker["evidence"])

    def test_spec_steward_is_running_but_live_gated(self):
        worker = self.workers[197]
        self.assertEqual(worker["status"], "running")
        self.assertIn("agentos-core:spec-steward-live-acceptance", worker["blocking_scope"])
        self.assertIn("docs/SPEC_STEWARD_O3_LIVE_RUNBOOK.md", worker["evidence"])
        self.assertIn("pull/208", worker["evidence"])
        self.assertIn("static CI as live acceptance", worker["non_authorities"])

    def test_persistent_supervisor_is_running_and_uses_197_as_live_acceptance(self):
        worker = self.workers[200]
        self.assertEqual(worker["status"], "running")
        self.assertIn("agentos-core:core-supervisor-live-verification", worker["blocking_scope"])
        self.assertIn(197, worker["related_issues"])
        edge = {
            "from": "agentos-core#200:live-acceptance",
            "to": "agentos-core#197",
        }
        self.assertIn(edge, self.graph["dependency_edges"])

    def test_live_runtime_authority_remains_separate_from_worker_status(self):
        authority = self.graph["authority"]["live_runtime_authority"]
        self.assertIsInstance(authority.get("generation"), int)
        self.assertGreater(authority["generation"], 0)
        self.assertRegex(str(authority.get("source_sha") or ""), r"^[0-9a-f]{40}$")
        self.assertNotIn("status", authority)


if __name__ == "__main__":
    unittest.main()
