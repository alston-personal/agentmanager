from __future__ import annotations

import json
import unittest
from pathlib import Path

from market_learning.replay import MarketReplay, ReplaySnapshot
from market_learning.strategy_delta import resolve_strategy
from market_learning.tournament import ReplayTournament


ROOT = Path(__file__).resolve().parents[1] / "market_learning" / "strategies"


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


ROWS = [
    {"instrument": "2454", "date": "2023-01-02", "open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0},
    {"instrument": "2454", "date": "2023-01-03", "open": 99.0, "high": 101.0, "low": 97.0, "close": 98.0},
    {"instrument": "2454", "date": "2023-01-04", "open": 98.0, "high": 100.0, "low": 96.0, "close": 97.0},
    {"instrument": "2454", "date": "2023-01-05", "open": 97.0, "high": 98.0, "low": 93.0, "close": 94.0},
    {"instrument": "2454", "date": "2023-01-06", "open": 94.0, "high": 95.0, "low": 91.0, "close": 92.0},
]


def feature_provider(snapshot: ReplaySnapshot):
    # Synthetic, deterministic feature frame for tournament-contract tests.
    # It deliberately creates disagreement between flow and momentum masters.
    assert all(row["date"] <= snapshot.cutoff_date for row in snapshot.rows)
    return {
        "price_action": 0.70,
        "volume": 0.20,
        "foreign_flow": -0.90,
        "margin": -0.30,
        "ownership_distribution": -0.80,
        "market_regime": 0.10,
    }


class ReplayTournamentTests(unittest.TestCase):
    def seed_strategies(self):
        base = load("base_behavioral_v1.json")
        return [
            resolve_strategy(base, load("flow_v1.delta.json")),
            resolve_strategy(base, load("momentum_v1.delta.json")),
            resolve_strategy(base, load("reversal_v1.delta.json")),
            resolve_strategy(base, load("neutral_v1.delta.json")),
        ]

    def test_same_snapshot_produces_master_disagreement(self):
        tournament = ReplayTournament(MarketReplay(ROWS), self.seed_strategies(), feature_provider)
        round_ = tournament.run_round(cutoff_date="2023-01-04", horizon_trading_days=2)
        directions = {entry.strategy_id: entry.prediction.direction for entry in round_.entries}
        self.assertEqual(directions["master-flow-v1"], "DOWN")
        self.assertEqual(directions["master-momentum-v1"], "UP")
        self.assertGreaterEqual(len(set(directions.values())), 2)

    def test_all_masters_receive_identical_feature_frame_and_outcome(self):
        tournament = ReplayTournament(MarketReplay(ROWS), self.seed_strategies(), feature_provider)
        round_ = tournament.run_round(cutoff_date="2023-01-04", horizon_trading_days=2)
        frames = [entry.prediction.evidence["feature_values"] for entry in round_.entries]
        self.assertTrue(all(frame == frames[0] for frame in frames))
        outcome_ids = {(entry.outcome.start_date, entry.outcome.end_date, entry.outcome.return_pct) for entry in round_.entries}
        self.assertEqual(len(outcome_ids), 1)

    def test_ranking_rewards_correct_high_confidence_direction(self):
        tournament = ReplayTournament(MarketReplay(ROWS), self.seed_strategies(), feature_provider)
        round_ = tournament.run_round(cutoff_date="2023-01-04", horizon_trading_days=2)
        self.assertEqual(round_.entries[0].outcome.actual_direction, "DOWN")
        ranking = round_.ranking()
        score_by_id = dict(ranking)
        self.assertGreater(score_by_id["master-flow-v1"], score_by_id["master-momentum-v1"])

    def test_round_is_reproducible(self):
        tournament = ReplayTournament(MarketReplay(ROWS), self.seed_strategies(), feature_provider)
        a = tournament.run_round(cutoff_date="2023-01-04", horizon_trading_days=2)
        b = tournament.run_round(cutoff_date="2023-01-04", horizon_trading_days=2)
        ids_a = [entry.prediction.prediction_id for entry in a.entries]
        ids_b = [entry.prediction.prediction_id for entry in b.entries]
        self.assertEqual(ids_a, ids_b)


if __name__ == "__main__":
    unittest.main()
