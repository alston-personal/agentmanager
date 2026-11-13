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
        self.git("init", "-q", "-b", "main", self.root, cwd=self.tmp.name)
        self.git("config", "user.name", "CI")
        self.git("config", "user.email", "ci@example.invalid")
        Path(self.root, "evidence.txt").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.initial = self.git("rev-parse", "HEAD")
        self.git("branch", "work", self.initial)
        Path(self.root, "evidence.txt").write_text("main advanced\n")
        self.git("commit", "-qam", "main advance")
        self.main = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.main)
        self.git("checkout", "-q", "work")
        Path(self.root, "work.txt").write_text("web gpt continued stale PR\n")
        self.git("add", ".")
        self.git("commit", "-qm", "stale work")
        self.stale = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "fresh", self.main)
        Path(self.root, "fresh.txt").write_text("new work on main\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fresh work")
        self.fresh = self.git("rev-parse", "HEAD")

    def git(self, *args, cwd=None):
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
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        with self.assertRaisesRegex(FreshnessError, "GIT_EVIDENCE_UNAVAILABLE"):
            self.gate(self.fresh)


    def test_protected_main_realm_actions_remain_registered(self):
        # Cross-PR safeguard: stale work must not replace the canonical
        # Realm installer/status with LEGACY_ACTION_REQUIRES_CONVERGENCE.
        from agentos_node.action_relay import ACTIONS
        from agentos_node import action_relay as relay

        bindings = {
            "agentos.realm-fabric.claim_deployment": relay._claim_realm_fabric_deployment,
            "agentos.realm-fabric.deployment_status": relay._realm_fabric_deployment_status,
            "agentos.realm-fabric.install_release": relay._install_realm_fabric_release,
            "agentos.realm-fabric.release_deployment": relay._release_realm_fabric_deployment,
        }
        for action, handler in bindings.items():
            with self.subTest(action=action):
                self.assertIs(ACTIONS[action], handler)
        self.assertIn(
            "realm-fabric-effective-unit-fence/v1",
            Path(relay.__file__).read_text(encoding="utf-8"),
        )

    def test_relay_consumer_manifest_matches_live_main_source_handlers(self):
        import json
        from agentos_node.action_relay import ACTIONS
        from agentos_node import action_relay as relay

        root = Path(__file__).resolve().parents[1]
        path = root / "docs/governance/branch-1682-legacy-relay-consumers.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(report["legacy_actions"]), 6)
        for row in report["legacy_actions"]:
            with self.subTest(action=row["action"]):
                self.assertEqual(row["candidate_behavior"],
                                 "PRESERVE_CANONICAL_MAIN_IMPLEMENTATION")
                self.assertIsNot(ACTIONS[row["action"]],
                                 getattr(relay, "_legacy_action_requires_convergence", None))
                self.assertFalse(row["allowed_for_promotion"])
        self.assertIn("ORACLE_INSTALLED_REVISION_UNVERIFIED",
                      report["legacy_actions"][0]["production_equivalence"])

    def test_main_runtime_repair_and_new_executor_providers_survive_resume_guard(self):
        from agent_core import realm_server
        from agentos_node import executor_job_action_relay as jobs

        self.assertTrue(hasattr(realm_server, "_GITHUB_MAIN_RUNTIME_REPAIR_WORKFLOW_REF"))
        self.assertTrue(hasattr(jobs, "DEPLOYMENT_INSPECT_PROVIDERS_REGISTERED"))
        self.assertTrue(hasattr(jobs, "COLAB_H3_SMOKE_PROVIDER_REGISTERED"))
        self.assertIn("CODE_MAINLINE_EVIDENCE_UNAVAILABLE",
                      Path(jobs.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
