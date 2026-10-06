from __future__ import annotations

import unittest

from market_learning.data_loader import TwseInstitutionalFlowLoader, merge_daily_signals
from market_learning.features import bar_feature_frame
from market_learning.replay import ReplaySnapshot


T86_FIXTURE = {
    "stat": "OK",
    "fields": [
        "證券代號",
        "證券名稱",
        "外陸資買進股數(不含外資自營商)",
        "外陸資賣出股數(不含外資自營商)",
        "外陸資買賣超股數(不含外資自營商)",
        "外資自營商買進股數",
        "外資自營商賣出股數",
        "外資自營商買賣超股數",
        "投信買進股數",
        "投信賣出股數",
        "投信買賣超股數",
        "自營商買賣超股數",
        "自營商買進股數(自行買賣)",
        "自營商賣出股數(自行買賣)",
        "自營商買賣超股數(自行買賣)",
        "自營商買進股數(避險)",
        "自營商賣出股數(避險)",
        "自營商買賣超股數(避險)",
        "三大法人買賣超股數",
    ],
    "data": [
        [
            "2454", "聯發科",
            "10,000,000", "7,000,000", "3,000,000",
            "0", "0", "0",
            "1,500,000", "500,000", "1,000,000",
            "-250,000",
            "100,000", "50,000", "50,000",
            "300,000", "600,000", "-300,000",
            "3,750,000",
        ]
    ],
}


class TwseInstitutionalFlowTests(unittest.TestCase):
    def test_normalize_t86_for_one_stock(self) -> None:
        loader = TwseInstitutionalFlowLoader()
        row = loader.normalize("2454", "2026-10-05", T86_FIXTURE)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["instrument"], "2454")
        self.assertEqual(row["foreign_net"], 3_000_000)
        self.assertEqual(row["investment_trust_net"], 1_000_000)
        self.assertEqual(row["dealer_net"], -250_000)
        self.assertEqual(row["total_institutional_net"], 3_750_000)

    def test_merge_and_feature_frame_exposes_foreign_flow(self) -> None:
        bars = [
            {
                "instrument": "2454",
                "date": "2026-10-05",
                "close": 100.0,
                "trade_volume": 10_000_000,
            },
            {
                "instrument": "2454",
                "date": "2026-10-06",
                "close": 101.0,
                "trade_volume": 10_000_000,
            },
            {
                "instrument": "2454",
                "date": "2026-10-07",
                "close": 102.0,
                "trade_volume": 10_000_000,
            },
        ]
        signals = [
            {
                "instrument": "2454",
                "date": "2026-10-05",
                "foreign_net": 1_000_000,
            },
            {
                "instrument": "2454",
                "date": "2026-10-06",
                "foreign_net": 2_000_000,
            },
            {
                "instrument": "2454",
                "date": "2026-10-07",
                "foreign_net": 3_000_000,
            },
        ]
        merged = merge_daily_signals(bars, signals)
        frame = bar_feature_frame(
            ReplaySnapshot("2454", "2026-10-07", tuple(merged))
        )
        self.assertIn("foreign_flow", frame.available)
        self.assertGreater(frame.values["foreign_flow"], 0)
        self.assertNotIn("foreign_flow", frame.missing)


if __name__ == "__main__":
    unittest.main()
