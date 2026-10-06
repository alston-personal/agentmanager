from __future__ import annotations

import unittest

from market_learning.features import bar_feature_frame
from market_learning.replay import ReplaySnapshot


class MarketFeatureTests(unittest.TestCase):
    def test_bar_features_use_only_snapshot_rows(self) -> None:
        rows = tuple(
            {
                "instrument": "2454",
                "date": f"2023-01-{day:02d}",
                "close": 100.0 + day,
                "trade_volume": 1000 + day * 100,
            }
            for day in range(2, 12)
        )
        snapshot = ReplaySnapshot("2454", "2023-01-11", rows)
        frame = bar_feature_frame(snapshot)
        self.assertGreater(frame.values["price_action"], 0)
        self.assertIn("volume", frame.available)
        self.assertIn("market_regime", frame.available)
        self.assertIn("foreign_flow", frame.missing)
        self.assertIn("ownership_distribution", frame.missing)

    def test_missing_volume_is_not_fabricated(self) -> None:
        snapshot = ReplaySnapshot(
            "2454",
            "2023-01-03",
            (
                {"instrument": "2454", "date": "2023-01-02", "close": 100.0},
                {"instrument": "2454", "date": "2023-01-03", "close": 101.0},
            ),
        )
        frame = bar_feature_frame(snapshot)
        self.assertNotIn("volume", frame.values)
        self.assertIn("volume", frame.missing)

    def test_feature_values_are_bounded(self) -> None:
        snapshot = ReplaySnapshot(
            "2454",
            "2023-01-04",
            (
                {"instrument": "2454", "date": "2023-01-02", "close": 10.0, "trade_volume": 100.0},
                {"instrument": "2454", "date": "2023-01-03", "close": 20.0, "trade_volume": 100.0},
                {"instrument": "2454", "date": "2023-01-04", "close": 40.0, "trade_volume": 10000.0},
            ),
        )
        frame = bar_feature_frame(snapshot)
        self.assertLessEqual(abs(frame.values["price_action"]), 1.0)
        self.assertLessEqual(abs(frame.values["volume"]), 1.0)
        self.assertLessEqual(abs(frame.values["market_regime"]), 1.0)


if __name__ == "__main__":
    unittest.main()
