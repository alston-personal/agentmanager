from __future__ import annotations

import json
import unittest
from pathlib import Path

from market_learning.strategy_delta import resolve_strategy


ROOT = Path(__file__).resolve().parents[1] / "market_learning" / "strategies"


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class MarketStrategyDeltaTests(unittest.TestCase):
    def test_seed_masters_resolve_deterministically_and_differ(self) -> None:
        base = load("base_behavioral_v1.json")
        names = [
            "flow_v1.delta.json",
            "momentum_v1.delta.json",
            "reversal_v1.delta.json",
            "neutral_v1.delta.json",
        ]
        instances = [resolve_strategy(base, load(name)) for name in names]
        fingerprints = {x.fingerprint for x in instances}
        self.assertEqual(len(fingerprints), 4)

        again = resolve_strategy(base, load("flow_v1.delta.json"))
        self.assertEqual(instances[0].fingerprint, again.fingerprint)

    def test_flow_master_changes_only_declared_semantics(self) -> None:
        base = load("base_behavioral_v1.json")
        flow = resolve_strategy(base, load("flow_v1.delta.json")).resolved
        self.assertEqual(flow["features"]["foreign_flow"], 1.8)
        self.assertEqual(flow["features"]["price_action"], 0.7)
        self.assertEqual(flow["prediction"]["min_confidence"], 0.55)
        self.assertIn("ownership_migration", flow["patterns"]["preferred"])

    def test_wrong_base_reference_is_rejected(self) -> None:
        base = load("base_behavioral_v1.json")
        delta = load("flow_v1.delta.json")
        delta["base_ref"] = "other"
        with self.assertRaises(ValueError):
            resolve_strategy(base, delta)


if __name__ == "__main__":
    unittest.main()
