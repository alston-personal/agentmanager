from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from .replay import EvaluationIR, MarketReplay, OutcomeIR, PredictionIR, ReplaySnapshot, ReviewIR
from .strategy_delta import StrategyInstance


FeatureProvider = Callable[[ReplaySnapshot], Mapping[str, float]]


def weighted_feature_predictor(
    snapshot: ReplaySnapshot,
    strategy: StrategyInstance,
    horizon_trading_days: int,
    features: Mapping[str, float],
) -> PredictionIR:
    weights = dict(strategy.resolved.get("features") or {})
    numerator = 0.0
    denominator = 0.0
    contributions: dict[str, float] = {}

    for name, raw_weight in weights.items():
        try:
            weight = float(raw_weight)
            value = float(features.get(name, 0.0))
        except (TypeError, ValueError):
            continue
        contribution = weight * value
        contributions[name] = contribution
        numerator += contribution
        denominator += abs(weight)

    if denominator <= 0:
        direction = "ABSTAIN"
        confidence = 0.0
        normalized_score = 0.0
    else:
        normalized_score = numerator / denominator
        threshold = float(strategy.resolved.get("prediction", {}).get("abstain_score_threshold", 0.05))
        if abs(normalized_score) < threshold:
            direction = "ABSTAIN"
            confidence = min(0.5, abs(normalized_score))
        else:
            direction = "UP" if normalized_score > 0 else "DOWN"
            confidence = min(0.99, 0.5 + min(abs(normalized_score), 1.0) * 0.49)

    return PredictionIR(
        instrument=snapshot.instrument,
        cutoff_date=snapshot.cutoff_date,
        horizon_trading_days=horizon_trading_days,
        direction=direction,
        confidence=confidence,
        strategy_id=strategy.strategy_id,
        evidence={
            "strategy_fingerprint": strategy.fingerprint,
            "feature_values": dict(features),
            "weighted_contributions": contributions,
            "normalized_score": normalized_score,
        },
    )


@dataclass(frozen=True)
class TournamentEntry:
    strategy_id: str
    prediction: PredictionIR
    outcome: OutcomeIR
    evaluation: EvaluationIR
    review: ReviewIR

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "prediction": self.prediction.to_dict(),
            "outcome": self.outcome.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "review": self.review.to_dict(),
        }


@dataclass(frozen=True)
class TournamentRound:
    instrument: str
    cutoff_date: str
    horizon_trading_days: int
    entries: tuple[TournamentEntry, ...]
    schema: str = "agentos.market-replay-tournament-round/v1"

    def ranking(self) -> list[tuple[str, float]]:
        scored = []
        for entry in self.entries:
            score = entry.evaluation.signed_score
            scored.append((entry.strategy_id, float(score) if score is not None else -999.0))
        return sorted(scored, key=lambda item: (-item[1], item[0]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "instrument": self.instrument,
            "cutoff_date": self.cutoff_date,
            "horizon_trading_days": self.horizon_trading_days,
            "entries": [entry.to_dict() for entry in self.entries],
            "ranking": [{"strategy_id": sid, "score": score} for sid, score in self.ranking()],
        }


class ReplayTournament:
    def __init__(
        self,
        replay: MarketReplay,
        strategies: Sequence[StrategyInstance],
        feature_provider: FeatureProvider,
    ) -> None:
        if not strategies:
            raise ValueError("at least one strategy is required")
        ids = [item.strategy_id for item in strategies]
        if len(ids) != len(set(ids)):
            raise ValueError("strategy IDs must be unique")
        self.replay = replay
        self.strategies = tuple(strategies)
        self.feature_provider = feature_provider

    def run_round(
        self,
        *,
        cutoff_date: str,
        horizon_trading_days: int,
        lookback: int | None = None,
    ) -> TournamentRound:
        snapshot = self.replay.snapshot(cutoff_date, lookback=lookback)
        features = dict(self.feature_provider(snapshot))
        entries: list[TournamentEntry] = []

        for strategy in self.strategies:
            prediction = weighted_feature_predictor(
                snapshot,
                strategy,
                horizon_trading_days,
                features,
            )
            outcome = self.replay.reveal(prediction)
            evaluation = self.replay.evaluate(prediction, outcome)
            review = self.replay.review(prediction, outcome, evaluation)
            entries.append(
                TournamentEntry(
                    strategy_id=strategy.strategy_id,
                    prediction=prediction,
                    outcome=outcome,
                    evaluation=evaluation,
                    review=review,
                )
            )

        return TournamentRound(
            instrument=self.replay.instrument,
            cutoff_date=cutoff_date,
            horizon_trading_days=horizon_trading_days,
            entries=tuple(entries),
        )
