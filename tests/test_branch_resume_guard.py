"""Concrete Git graph tests: resume gate prevents stale Executor code work."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.branch_resume_guard import FreshnessError, inspect


class BranchResumeGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name) / "repo")
        self.run("init", "-q", "-b", "main", self.root, cwd=self.tmp.name)
        self.run("config", "user.name", "CI")
        self.run("config", "user.email", "ci@example.invalid")
        Path(self.root, "evidence.txt").write_text("base\n")
        self.run("add", ".")
        self.run("commit", "-qm", "initial")
        self.initial = self.run("rev-parse", "HEAD")
        self.run("branch", "work", self.initial)
        Path(self.root, "evidence.txt").write_text("main advanced\n")
        self.run("commit", "-qam", "main advance")
        self.main = self.run("rev-parse", "HEAD")
        self.run("update-ref", "refs/remotes/origin/main", self.main)
        self.run("checkout", "-q", "work")
        Path(self.root, "work.txt").write_text("web gpt continued stale PR\n")
        self.run("add", ".")
        self.run("commit", "-qm", "stale work")
        self.stale = self.run("rev-parse", "HEAD")
        self.run("checkout", "-q", "-b", "fresh", self.main)
        Path(self.root, "fresh.txt").write_text("new work on main\n")
        self.run("add", ".")
        self.run("commit", "-qm", "fresh work")
        self.fresh = self.run("rev-parse", "HEAD")

    def run(self, *args, cwd=None):
        res = subprocess.run(["git", *args], cwd=cwd or self.root,
                             text=True, capture_output=True, check=True)
        return res.stdout.strip()

    def gate(self, sha, kind="code"):
        return inspect(root=self.root, main_ref="refs/remotes/origin/main",
                       work_ref=sha, kind=kind)

    def test_blocks_stale_wow_pr_even_if_own_commit_is_newer(self):
        result = self.gate(self.stale)
        self.assertEqual(result["status"], "RECONCILE_REQUIRED")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["main_sha"], self.main)
        self.assertEqual(result["merge_base_sha"], self.initial)

    def test_accepts_fresh_mainline_descendant(self):
        result = self.gate(self.fresh)
        self.assertEqual(result["status"], "MAINLINE_CURRENT")
        self.assertTrue(result["allowed"])
        self.assertFalse(result["production_authorized"])

    def test_safe_read_only_inventory_allowed_even_if_stale(self):
        result = self.gate(self.stale, "read_only")
        self.assertEqual(result["status"], "READ_ONLY_INSPECT")
        self.assertTrue(result["allowed"])

    def test_legacy_production_is_not_authorized_by_branch_membership(self):
        result = self.gate(self.fresh, "legacy_production")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], "GOVERNED_LEGACY_EXCEPTION_REQUIRED")

    def test_pinned_sha_and_authoritative_remote_required(self):
        with self.assertRaisesRegex(FreshnessError, "UNPINNED_WORK_SHA"):
            self.gate("HEAD")
        with self.assertRaisesRegex(FreshnessError, "UNTRUSTED_MAIN_REF"):
            inspect(root=self.root, main_ref="refs/heads/work",
                    work_ref=self.fresh, kind="code")
        self.run("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaisesRegex(FreshnessError, "GIT_EVIDENCE_UNAVAILABLE"):
            self.gate(self.fresh)


if __name__ == "__main__":
    unittest.main()
