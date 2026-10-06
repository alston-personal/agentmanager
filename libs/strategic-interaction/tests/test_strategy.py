from __future__ import annotations

import unittest

from strategic_interaction import StrategyDelta, StrategySpec, resolve_strategy


class StrategicStrategyTests(unittest.TestCase):
    def test_delta_resolution_is_deterministic(self) -> None:
        base = StrategySpec(
            strategy_id="base",
            parameters={"weights": {"flow": 1.0, "momentum": 1.0}, "patterns": []},
        )
        delta = StrategyDelta(
            delta_id="flow-heavy",
            base_ref="base",
            strategy_id="master-flow",
            set_values={"weights.flow": 1.8},
            add_values={"patterns": ("accumulation",)},
        )
        a = resolve_strategy(base, delta)
        b = resolve_strategy(base, delta)
        self.assertEqual(a.fingerprint, b.fingerprint)
        self.assertEqual(a.parameters["weights"]["flow"], 1.8)
        self.assertIn("accumulation", a.parameters["patterns"])


if __name__ == "__main__":
    unittest.main()
