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
