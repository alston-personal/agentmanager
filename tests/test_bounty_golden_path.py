import os
import json
import unittest
from agentos.bounty.golden_path import BountyGoldenPath

class TestBountyGoldenPath(unittest.TestCase):
    def setUp(self):
        self.test_ledger = "test_bounty_ledger.json"
        self.bounty_path = BountyGoldenPath(ledger_path=self.test_ledger)

    def tearDown(self):
        if os.path.exists(self.test_ledger):
            os.remove(self.test_ledger)

    def test_evaluate_candidate_assigned_exclusion(self):
        issue = {
            "id": "tt-metal-#58986",
            "title": "Fix kernel dispatch",
            "assignee": "other_contributor",
            "state": "open",
            "sponsor": "Tenstorrent",
            "reward_usd": 1000
        }
        res = self.bounty_path.evaluate_candidate(issue)
        self.assertFalse(res["qualified"])
        self.assertIn("assigned", res["reason"].lower())

    def test_evaluate_candidate_crowded_exclusion(self):
        issue = {
            "id": "tt-metal-#8621",
            "title": "Memory optimization",
            "assignee": None,
            "state": "open",
            "crowded": True,
            "sponsor": "Tenstorrent",
            "reward_usd": 500
        }
        res = self.bounty_path.evaluate_candidate(issue)
        self.assertFalse(res["qualified"])
        self.assertIn("crowded", res["reason"].lower())

    def test_evaluate_candidate_success(self):
        issue = {
            "id": "tt-metal-#99999",
            "title": "Clean implementation",
            "assignee": None,
            "state": "open",
            "crowded": False,
            "sponsor": "Tenstorrent",
            "reward_usd": 1500,
            "ai_assisted_prohibited": False
        }
        res = self.bounty_path.evaluate_candidate(issue)
        self.assertTrue(res["qualified"])
        self.assertIn("receipt", res)
        self.assertTrue(os.path.exists(self.test_ledger))

if __name__ == "__main__":
    unittest.main()
