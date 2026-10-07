from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pr_backlog_reconcile", ROOT / "scripts" / "pr_backlog_reconcile.py")
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)


class PrBacklogReconcileTests(unittest.TestCase):
    def base(self, **overrides):
        row = {
            "number": 1,
            "title": "example",
            "url": "https://example.invalid/1",
            "updated_at": "2026-10-06T00:00:00Z",
            "body": "",
            "ahead_by": 2,
            "behind_by": 1,
            "mergeable_state": "clean",
            "files": 2,
        }
        row.update(overrides)
        return row

    def test_recent_clean_pr_is_active(self):
        got = mod.classify(self.base(), now=NOW)
        self.assertEqual(got["status"], "ACTIVE")

    def test_no_unique_commits_is_already_landed(self):
        got = mod.classify(self.base(ahead_by=0), now=NOW)
        self.assertEqual(got["status"], "ALREADY_LANDED")

    def test_conflicted_pr_is_blocked(self):
        got = mod.classify(self.base(mergeable_state="dirty"), now=NOW)
        self.assertEqual(got["status"], "BLOCKED")

    def test_old_clean_pr_requires_review(self):
        got = mod.classify(
            self.base(updated_at="2026-08-01T00:00:00Z", behind_by=600),
            now=NOW,
        )
        self.assertEqual(got["status"], "NEEDS_REVIEW")
        self.assertTrue(any("behind_main_by_600_commits" == x for x in got["reasons"]))

    def test_explicit_rebased_follow_up_marks_old_pr_superseded(self):
        old = self.base(number=1027, title="same")
        new = self.base(
            number=1028,
            title="same",
            body="Rebased follow-up to #1027 on latest main.",
        )
        report = mod.reconcile([old, new], now=NOW)
        rows = {row["number"]: row for row in report["rows"]}
        self.assertEqual(rows[1027]["status"], "SUPERSEDED")
        self.assertEqual(rows[1027]["superseded_by"], 1028)

    def test_plain_follow_up_does_not_imply_supersession(self):
        old = self.base(number=10)
        new = self.base(number=11, body="Dependent follow-up to #10")
        report = mod.reconcile([old, new], now=NOW)
        rows = {row["number"]: row for row in report["rows"]}
        self.assertNotEqual(rows[10]["status"], "SUPERSEDED")

    def test_report_is_dry_run(self):
        report = mod.reconcile([self.base()], now=NOW)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["counts"], {"ACTIVE": 1})


if __name__ == "__main__":
    unittest.main()
