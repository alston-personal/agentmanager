from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CoreRuntimeOwnershipTests(unittest.TestCase):
    def test_shared_checkout_is_source_cache_only(self):
        policy = json.loads((ROOT / ".agent/governance/runtime_ownership.json").read_text(encoding="utf-8"))
        shared = policy["shared_source_checkout"]
        self.assertEqual(shared["path"], "/home/ubuntu/agentmanager")
        self.assertFalse(shared["production_runtime_allowed"])

    def test_core_has_immutable_release_contract(self):
        policy = json.loads((ROOT / ".agent/governance/runtime_ownership.json").read_text(encoding="utf-8"))
        core = policy["services"]["agentos-core"]
        self.assertEqual(core["release_root"], "/home/ubuntu/agent-data/releases/core")
        self.assertEqual(core["live_pointer"], "/home/ubuntu/agent-data/runtime/core/current")
        self.assertNotEqual(core["release_root"], policy["shared_source_checkout"]["path"])

    def test_core_deployer_must_use_release_worktree(self):
        source = (ROOT / ".github/workflows/deploy-agentos-core.yml").read_text(encoding="utf-8")
        self.assertIn('RELEASE_ROOT="$DATA_ROOT/releases/core"', source)
        self.assertIn('CURRENT_LINK="$DATA_ROOT/runtime/core/current"', source)
        self.assertIn('git worktree add --detach "$RELEASE" "$TARGET_SHA"', source)
        self.assertIn('--project-root "$RELEASE"', source)
        self.assertNotIn('git checkout --detach "$TARGET_SHA"', source)
        self.assertNotIn('python3 -m pip install -e .', source)


if __name__ == "__main__":
    unittest.main()
