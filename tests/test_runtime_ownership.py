from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeOwnershipPolicyTests(unittest.TestCase):
    def test_registry_declares_shared_checkout_non_runtime(self):
        policy = json.loads((ROOT / ".agent/governance/runtime_ownership.json").read_text(encoding="utf-8"))
        self.assertFalse(policy["shared_source_checkout"]["production_runtime_allowed"])
        self.assertEqual(policy["shared_source_checkout"]["path"], "/home/ubuntu/agentmanager")
        self.assertIn("dashboard", policy["services"])
        self.assertNotEqual(
            policy["services"]["dashboard"]["release_root"],
            policy["shared_source_checkout"]["path"],
        )

    def test_guard_contains_hard_mutation_detectors(self):
        source = (ROOT / "scripts/check_runtime_ownership.py").read_text(encoding="utf-8")
        for token in (
            "reset\\s+--hard",
            "checkout",
            "switch",
            "copies/moves files into shared",
            "launches a process manager from mutable shared checkout",
            "--cwd",
        ):
            self.assertIn(token, source)

    def test_dashboard_declares_immutable_runtime_controller(self):
        policy = json.loads((ROOT / ".agent/governance/runtime_ownership.json").read_text(encoding="utf-8"))
        dashboard = policy["services"]["dashboard"]
        self.assertEqual(dashboard["process_name"], "agentos-dashboard")
        self.assertEqual(dashboard["runtime_controller"], "scripts/deploy_dashboard_release.sh")
        self.assertEqual(dashboard["config_path"], "/home/ubuntu/.config/milkcat/dashboard.env.local")
        self.assertNotIn("/home/ubuntu/agentmanager/dashboard", dashboard["live_pointer"])

    def test_dashboard_release_controller_never_starts_pm2_from_legacy_path(self):
        source = (ROOT / "scripts/deploy_dashboard_release.sh").read_text(encoding="utf-8")
        self.assertIn('APP_NAME="agentos-dashboard"', source)
        self.assertIn('RELEASE_ROOT="/home/ubuntu/agent-data/releases/dashboard/apps"', source)
        self.assertIn('node "$PM2_CLI" start /usr/bin/npm --name "$APP_NAME" --cwd "$RELEASE" -- start', source)
        self.assertNotIn('--cwd "$LEGACY"', source)
        self.assertIn("dashboard_shared_build_independence=PASS", source)

    def test_each_declared_service_has_owner_lock_release_root(self):
        policy = json.loads((ROOT / ".agent/governance/runtime_ownership.json").read_text(encoding="utf-8"))
        for name, service in policy["services"].items():
            with self.subTest(service=name):
                self.assertTrue(service["owner"])
                self.assertTrue(service["release_root"])
                self.assertTrue(service["live_pointer"])
                self.assertTrue(service["lock"])


if __name__ == "__main__":
    unittest.main()
