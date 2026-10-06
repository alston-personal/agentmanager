from __future__ import annotations

import unittest

from market_learning.replay import MarketReplay, PredictionIR, ReplaySnapshot


ROWS = [
    {"instrument": "2454", "date": "2023-05-08", "open": 700.0, "high": 710.0, "low": 695.0, "close": 705.0},
    {"instrument": "2454", "date": "2023-05-09", "open": 706.0, "high": 715.0, "low": 700.0, "close": 712.0},
    {"instrument": "2454", "date": "2023-05-10", "open": 713.0, "high": 718.0, "low": 704.0, "close": 708.0},
    {"instrument": "2454", "date": "2023-05-11", "open": 706.0, "high": 709.0, "low": 690.0, "close": 694.0},
    {"instrument": "2454", "date": "2023-05-12", "open": 692.0, "high": 698.0, "low": 680.0, "close": 684.0},
    {"instrument": "2454", "date": "2023-05-15", "open": 686.0, "high": 690.0, "low": 675.0, "close": 680.0},
]


def down_predictor(snapshot: ReplaySnapshot, strategy_id: str, horizon: int) -> PredictionIR:
    assert all(row["date"] <= snapshot.cutoff_date for row in snapshot.rows)
    return PredictionIR(
        instrument=snapshot.instrument,
        cutoff_date=snapshot.cutoff_date,
        horizon_trading_days=horizon,
        direction="DOWN",
        confidence=0.7,
        strategy_id=strategy_id,
        evidence={"latest_close": snapshot.latest["close"]},
    )


class MarketReplayTests(unittest.TestCase):
    def test_snapshot_cannot_include_future_rows(self) -> None:
        replay = MarketReplay(ROWS)
        snapshot = replay.snapshot("2023-05-10")
        self.assertEqual([row["date"] for row in snapshot.rows], ["2023-05-08", "2023-05-09", "2023-05-10"])

    def test_snapshot_rejects_manual_future_leakage(self) -> None:
        with self.assertRaises(ValueError):
            ReplaySnapshot(
                instrument="2454",
                cutoff_date="2023-05-10",
                rows=({"instrument": "2454", "date": "2023-05-11", "close": 694.0},),
            )

    def test_prediction_is_deterministic(self) -> None:
        replay = MarketReplay(ROWS)
        p1 = replay.run_prediction(
            cutoff_date="2023-05-10",
            horizon_trading_days=3,
            strategy_id="master-flow-v1",
            predictor=down_predictor,
        )
        p2 = replay.run_prediction(
            cutoff_date="2023-05-10",
            horizon_trading_days=3,
            strategy_id="master-flow-v1",
            predictor=down_predictor,
        )
        self.assertEqual(p1.prediction_id, p2.prediction_id)

    def test_reveal_evaluate_review(self) -> None:
        replay = MarketReplay(ROWS)
        prediction = replay.run_prediction(
            cutoff_date="2023-05-10",
            horizon_trading_days=3,
            strategy_id="master-flow-v1",
            predictor=down_predictor,
        )
        outcome = replay.reveal(prediction)
        evaluation = replay.evaluate(prediction, outcome)
        review = replay.review(prediction, outcome, evaluation)

        self.assertEqual(outcome.end_date, "2023-05-15")
        self.assertEqual(outcome.actual_direction, "DOWN")
        self.assertTrue(evaluation.direction_correct)
        self.assertEqual(evaluation.classification, "CORRECT")
        self.assertLess(evaluation.brier_score, 0.2)
        self.assertEqual(review.result, "CORRECT")

    def test_outcome_is_unavailable_before_horizon_exists(self) -> None:
        replay = MarketReplay(ROWS[:4])
        prediction = replay.run_prediction(
            cutoff_date="2023-05-10",
            horizon_trading_days=3,
            strategy_id="master-flow-v1",
            predictor=down_predictor,
        )
        with self.assertRaises(ValueError):
            replay.reveal(prediction)


if __name__ == "__main__":
    unittest.main()
