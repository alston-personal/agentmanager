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
        for token in ("reset\\s+--hard", "checkout", "switch", "copies/moves files into shared"):
            self.assertIn(token, source)

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
