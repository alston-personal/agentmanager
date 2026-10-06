from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from market_learning.data_loader import ImmutableRawArchive, TwseMonthlyStockLoader, roc_date_to_iso


FIXTURE = {
    "stat": "OK",
    "fields": ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數", "註記"],
    "data": [
        ["115/10/05", "1,234,000", "6,100,000,000", "5,000.00", "5,200.00", "4,950.00", "5,165.00", "+215.00", "12,345", ""],
        ["115/10/06", "2,000,000", "9,900,000,000", "5,080.00", "5,090.00", "4,900.00", "4,950.00", "-215.00", "18,765", ""],
    ],
}


class MarketHistoryLoaderTests(unittest.TestCase):
    def test_roc_date(self) -> None:
        self.assertEqual(roc_date_to_iso("115/10/06"), "2026-10-06")

    def test_normalize_stock_day(self) -> None:
        rows = TwseMonthlyStockLoader().normalize("2454", FIXTURE)
        self.assertEqual(rows[0]["instrument"], "2454")
        self.assertEqual(rows[0]["date"], "2026-10-05")
        self.assertEqual(rows[0]["close"], 5165.0)
        self.assertEqual(rows[1]["change"], -215.0)
        self.assertEqual(rows[1]["trade_volume"], 2_000_000)

    def test_immutable_archive_accepts_same_payload_and_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            archive = ImmutableRawArchive(td)
            first = archive.store(source="twse-stock-day", instrument="2454", request_key="2026-10", payload=FIXTURE)
            second = archive.store(source="twse-stock-day", instrument="2454", request_key="2026-10", payload=FIXTURE)
            self.assertEqual(first.sha256, second.sha256)

            changed = json.loads(json.dumps(FIXTURE))
            changed["data"][0][6] = "5,170.00"
            with self.assertRaises(ValueError):
                archive.store(source="twse-stock-day", instrument="2454", request_key="2026-10", payload=changed)

            self.assertTrue(Path(first.raw_path).exists())


if __name__ == "__main__":
    unittest.main()
