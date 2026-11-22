"""Recent GitHub Actions run triage never confuses CI status with deployment proof."""
import unittest
from unittest.mock import patch
import json
from scripts.audit_workflow_recent_runs import build_evidence, fetch_recent_runs


class RecentRunTriageTest(unittest.TestCase):
    def test_legacy_push_candidate_with_recent_activity_is_prioritized(self):
        provider = {
            "workflows": [
                {"workflow_id": 42, "path": ".github/workflows/legacy.yml",
                 "provider_state": "active", "legacy_push": True,
                 "mutating_signal": True},
                {"workflow_id": 88, "path": ".github/workflows/dormant.yml",
                 "provider_state": "active", "legacy_push": True,
                 "mutating_signal": True},
            ],
            "provider_not_in_either_branch": [
                {"workflow_id": 77, "path": ".github/workflows/orphan.yml",
                 "provider_state": "active"},
            ],
        }
        runs = [
            {"workflow_id": 42, "head_branch": "core/integration",
             "event": "push", "status": "completed", "conclusion": "success",
             "created_at": "2026-11-01T01:00:00Z"},
            {"workflow_id": 42, "head_branch": "main",
             "event": "workflow_dispatch", "status": "completed",
             "conclusion": "failure", "created_at": "2026-11-02T01:00:00Z"},
            {"workflow_id": 77, "head_branch": "archived/special",
             "event": "workflow_dispatch", "status": "completed",
             "conclusion": "success", "created_at": "2026-11-03T01:00:00Z"},
        ]
        d = build_evidence(provider, runs, "2026-10-23", False, len(runs))
        by_id = {x["workflow_id"]: x for x in d["records"]}
        self.assertEqual(by_id[42]["priority"], "p0_observed_legacy_push_candidate")
        self.assertEqual(by_id[42]["legacy_push_runs"], 1)
        self.assertEqual(by_id[42]["completed_successful_runs"], 1)
        self.assertEqual(by_id[88]["priority"], "p2_unobserved_legacy_candidate")
        self.assertNotIn("legacy_push_runs", by_id[88])
        self.assertEqual(by_id[77]["other_branch_runs"], 1)
        self.assertEqual(d["candidate_recent_legacy_push_count"], 1)

    def test_short_last_page_does_not_hide_github_result_window_cap(self):
        response = json.dumps({
            "total_count": 2500,
            "workflow_runs": [{"id": i} for i in range(80)],
        })
        with patch("scripts.audit_workflow_recent_runs.subprocess.check_output",
                   return_value=response) as mocked:
            rows, incomplete, total = fetch_recent_runs(
                "alston-personal/agentmanager", "2026-10-23", max_pages=30,
                branch="core/integration")
        self.assertEqual(len(rows), 80)
        self.assertEqual(total, 2500)
        self.assertTrue(incomplete)
        self.assertIn("branch=core%2Fintegration", mocked.call_args.args[0][2])

    def test_incomplete_history_does_not_become_zero_risk(self):
        provider = {"workflows": [{"workflow_id": 1,
            "path": ".github/workflows/legacy.yml", "provider_state": "active",
            "legacy_push": True, "mutating_signal": True}]}
        d = build_evidence(provider, [], "2026-10-23", True, 5000)
        self.assertTrue(d["pagination_incomplete"])
        self.assertEqual(d["records"][0]["priority"], "p2_unobserved_legacy_candidate")
        self.assertIn("No recent run != disabled", d["disclaimer"])


if __name__ == "__main__":
    unittest.main()
