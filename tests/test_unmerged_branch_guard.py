"""Unit tests for Unmerged Branch Guard."""
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.unmerged_branch_guard import audit_unmerged_branches


class TestUnmergedBranchGuard(unittest.TestCase):
    @patch("scripts.unmerged_branch_guard.get_unmerged_branches")
    @patch("scripts.unmerged_branch_guard.inspect_branch_drift")
    def test_audit_unmerged_branches_detects_stale_orphan(self, mock_inspect, mock_unmerged):
        mock_unmerged.return_value = ["feat/old-abandoned", "feat/fresh-active"]
        
        mock_inspect.side_effect = [
            {
                "branch": "feat/old-abandoned",
                "commit": "12345678",
                "last_commit_date": "2026-09-01T00:00:00+00:00",
                "days_idle": 30.0,
                "subject": "old feature",
                "has_changes": True,
            },
            {
                "branch": "feat/fresh-active",
                "commit": "87654321",
                "last_commit_date": "2026-11-26T00:00:00+00:00",
                "days_idle": 1.0,
                "subject": "fresh feature",
                "has_changes": True,
            },
        ]

        report = audit_unmerged_branches(Path("/dummy"), base_branch="main", max_idle_days=14.0)

        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["stale_orphaned_branches"], 1)
        self.assertEqual(report["active_feature_branches"], 1)
        self.assertEqual(report["anomalies"][0]["branch"], "feat/old-abandoned")
        self.assertIn("超過 30.0 天", report["anomalies"][0]["remediation"])

    @patch("scripts.unmerged_branch_guard.get_unmerged_branches")
    @patch("scripts.unmerged_branch_guard.inspect_branch_drift")
    def test_audit_unmerged_branches_clean(self, mock_inspect, mock_unmerged):
        mock_unmerged.return_value = ["feat/fresh-active"]
        mock_inspect.return_value = {
            "branch": "feat/fresh-active",
            "commit": "87654321",
            "last_commit_date": "2026-11-26T00:00:00+00:00",
            "days_idle": 1.0,
            "subject": "fresh feature",
            "has_changes": True,
        }

        report = audit_unmerged_branches(Path("/dummy"), base_branch="main", max_idle_days=14.0)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["stale_orphaned_branches"], 0)


if __name__ == "__main__":
    unittest.main()
