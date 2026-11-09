import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import audit_oracle_identity_boundaries as audit


class OracleIdentityBoundaryAuditTests(unittest.TestCase):
    def test_unbounded_cross_owner_mutation_is_p0(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            "scripts/example.sh",
            "AGENT_DATA_ROOT=/home/ubuntu/agent-data\nsystemctl --user restart x\nmv a b\nagentos-node",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["risk"], "P0")
        self.assertEqual(row["classification"], "unbounded-cross-owner-mutation")

    def test_user_systemd_shared_mutation_without_node_identity_is_p1_review(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            "scripts/example.sh",
            "AGENT_DATA_ROOT=/home/ubuntu/agent-data\nsystemctl --user restart x\nmv a b",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["risk"], "P1")
        self.assertEqual(row["classification"], "user-runtime-mutation-review")

    def test_explicit_group_boundary_removes_p0(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            "scripts/example.sh",
            "AGENT_DATA_ROOT=/home/ubuntu/agent-data\nsystemctl --user restart x\nmv a b\n/usr/bin/sg agentos -c",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertNotEqual(row["risk"], "P0")
        self.assertTrue(row["has_explicit_group_boundary"])

    def test_confirmed_migration_overrides_heuristic_classification(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        self.assertIn(".agent/scripts/agentos-core-supervisor.service", policy["confirmed_migrations"])

    def test_auditor_excludes_itself_from_runtime_findings(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        self.assertTrue(audit._excluded("scripts/audit_oracle_identity_boundaries.py", policy["audit_excludes"]))

    def test_review_override_downgrades_verified_protocol_boundary(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            ".github/workflows/oracle-exact-generation-executor-job-rollout.yml",
            "AGENT_DATA_ROOT=/home/ubuntu/agent-data\nagentos-node\nwrite_text(",
            policy,
        )
        self.assertEqual(row["risk"], "P0")
        override = policy["audit_overrides"][".github/workflows/oracle-exact-generation-executor-job-rollout.yml"]
        self.assertEqual(override["risk"], "P1")
        self.assertEqual(override["classification"], "governed-bootstrap-protocol-boundary")

    def test_structured_sg_and_systemd_group_are_bounded_markers(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        self.assertIn('["/usr/bin/sg", "agentos", "-c"', policy["bounded_group_markers"])
        self.assertIn("Group=agentos", policy["bounded_group_markers"])

    def test_interactive_ubuntu_path_is_classified_not_globally_banned(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            "scripts/install_gemini_web_bridge_user.sh",
            "PROFILE=/home/ubuntu/.config/chromium",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["classification"], "ubuntu-required-candidate")

    def test_closure_taxonomy_is_explicit(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            set(policy["closure_classifications"]),
            {"ubuntu-required", "dedicated-service-identity", "bounded-group-boundary", "static-false-positive"},
        )
        self.assertTrue(policy["closure_requirements"]["every_finding_requires_closure_classification"])

    def test_core_live_acceptance_uses_latest_accepted_audit(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        accepted = policy["live_acceptance"]["oracle_core_bundle"]
        self.assertEqual(accepted["runtime_audit_run"], 37394284772)
        self.assertEqual(accepted["immutable_count"], 10)
        self.assertEqual(accepted["mutable_count"], 0)
        self.assertEqual(accepted["other_count"], 0)
        self.assertEqual(accepted["result"], "PASS")

    def test_p0_baseline_is_explicit_and_not_approval(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        baseline = policy["p0_baseline"]
        self.assertEqual(len(baseline["paths"]), 0)
        self.assertIn("no reviewed oracle identity p0 paths remain", baseline["rule"].lower())

    def test_inventory_reports_new_unreviewed_p0_against_baseline(self):
        payload = audit.build_inventory()
        self.assertIn("new_unreviewed_p0", payload["summary"])
        self.assertEqual(payload["summary"]["new_unreviewed_p0"], [])
        self.assertEqual(len(payload["summary"]["p0_paths"]), 0)


if __name__ == "__main__":
    unittest.main()
