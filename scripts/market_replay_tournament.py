#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_learning.features import bar_feature_frame, bar_feature_provider
from market_learning.replay import MarketReplay
from market_learning.strategy_delta import resolve_strategy
from market_learning.tournament import ReplayTournament


STRATEGY_DIR = Path(__file__).resolve().parents[1] / "market_learning" / "strategies"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path, instrument: str):
    rows = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if str(row.get("instrument")) == instrument:
            rows.append(row)
    return rows


def seed_strategies():
    base = load_json(STRATEGY_DIR / "base_behavioral_v1.json")
    return [
        resolve_strategy(base, load_json(STRATEGY_DIR / name))
        for name in (
            "flow_v1.delta.json",
            "momentum_v1.delta.json",
            "reversal_v1.delta.json",
            "neutral_v1.delta.json",
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Market Replay Tournament round.")
    parser.add_argument("--data", required=True, help="Normalized JSONL from market_history_loader")
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--lookback", type=int, default=60)
    args = parser.parse_args()

    rows = load_rows(Path(args.data), args.instrument)
    replay = MarketReplay(rows)
    snapshot = replay.snapshot(args.cutoff, lookback=args.lookback)
    frame = bar_feature_frame(snapshot)

    tournament = ReplayTournament(replay, seed_strategies(), bar_feature_provider)
    round_ = tournament.run_round(
        cutoff_date=args.cutoff,
        horizon_trading_days=args.horizon,
        lookback=args.lookback,
    )

    output = round_.to_dict()
    output["feature_frame"] = frame.to_dict()
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
