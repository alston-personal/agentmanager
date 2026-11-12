from __future__ import annotations

import unittest
from unittest.mock import patch

from agent_core.runtime_ota_acceptance import accept_candidate

NODE = "test-node"
SHA = "a" * 40
OTHER = "b" * 40


class FakeFabric:
    def __init__(self):
        self.queued = []

    def queue_task(self, node_id, task):
        self.queued.append((node_id, task))

    def get_receipt(self, task_id):
        return {"ok": True, "task_id": task_id}


class FakeRegistry:
    def __init__(self, commits):
        self.commits = iter(commits)

    def load(self):
        commit = next(self.commits)
        return {"nodes": {NODE: {
            "status": "online",
            "runtime": {"source_commit": commit},
        }}}


class CandidateRecheckTests(unittest.TestCase):
    def attempt(self, commits):
        fabric = FakeFabric()
        registry = FakeRegistry(commits)
        with patch("agent_core.runtime_ota_acceptance.RealmFabricStore", return_value=fabric), \
             patch("agent_core.runtime_ota_acceptance.NodeRegistry", return_value=registry):
            result = accept_candidate(NODE, SHA, timeout_seconds=15)
        return result, fabric

    def test_probe_passes_and_candidate_still_active(self):
        result, fabric = self.attempt([SHA, SHA])
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "post_switch_probe")
        self.assertEqual(len(fabric.queued), 1)

    def test_probe_passes_but_candidate_rolled_back(self):
        result, fabric = self.attempt([SHA, OTHER])
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "post_switch_recheck")
        self.assertEqual(result["reason"], "candidate_no_longer_active")
        self.assertEqual(len(fabric.queued), 1)


if __name__ == "__main__":
    unittest.main()
