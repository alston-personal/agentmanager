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

    def test_incidental_agentos_node_reference_does_not_prove_p0_identity(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            "agentos_node/example.py",
            "REQUEST_OWNER='agentos-node'\nROOT='/home/ubuntu/agent-data'\nPath(ROOT).mkdir(parents=True)",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertNotEqual(row["risk"], "P0")

    def test_direct_oracle_runner_proves_node_execution_for_p0(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            ".github/workflows/example.yml",
            "runs-on: [self-hosted, Linux, ARM64, oracle]\nDATA=/home/ubuntu/agent-data\nmkdir -p $DATA/runtime/x",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["risk"], "P0")
        self.assertIn("direct-oracle-runner", row["tags"])

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

    def test_interactive_ubuntu_path_is_classified_not_globally_banned(self):
        policy = json.loads(audit.POLICY_PATH.read_text(encoding="utf-8"))
        row = audit._classify(
            "scripts/install_gemini_web_bridge_user.sh",
            "PROFILE=/home/ubuntu/.config/chromium",
            policy,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["classification"], "ubuntu-required-candidate")


if __name__ == "__main__":
    unittest.main()
