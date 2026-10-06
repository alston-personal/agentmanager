from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable, Mapping, Sequence


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"


def _direction(value: float) -> str:
    if value > 0:
        return "UP"
    if value < 0:
        return "DOWN"
    return "FLAT"


@dataclass(frozen=True)
class ReplaySnapshot:
    instrument: str
    cutoff_date: str
    rows: tuple[Mapping[str, Any], ...]
    schema: str = "agentos.market-replay-snapshot/v1"

    def __post_init__(self) -> None:
        for row in self.rows:
            row_date = str(row.get("date") or "")
            if row_date > self.cutoff_date:
                raise ValueError(
                    f"future leakage detected: row date {row_date} exceeds cutoff {self.cutoff_date}"
                )

    @property
    def latest(self) -> Mapping[str, Any]:
        if not self.rows:
            raise ValueError("snapshot has no rows")
        return self.rows[-1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "instrument": self.instrument,
            "cutoff_date": self.cutoff_date,
            "rows": [dict(row) for row in self.rows],
        }


@dataclass(frozen=True)
class PredictionIR:
    instrument: str
    cutoff_date: str
    horizon_trading_days: int
    direction: str
    confidence: float
    strategy_id: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    schema: str = "agentos.market-prediction/v1"
    prediction_id: str = ""

    def __post_init__(self) -> None:
        if self.direction not in {"UP", "DOWN", "FLAT", "ABSTAIN"}:
            raise ValueError(f"unsupported direction: {self.direction}")
        if self.horizon_trading_days < 1:
            raise ValueError("horizon_trading_days must be >= 1")
        if not 0 <= float(self.confidence) <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.prediction_id:
            payload = {
                "instrument": self.instrument,
                "cutoff_date": self.cutoff_date,
                "horizon_trading_days": self.horizon_trading_days,
                "direction": self.direction,
                "confidence": self.confidence,
                "strategy_id": self.strategy_id,
                "evidence": dict(self.evidence),
            }
            object.__setattr__(self, "prediction_id", _stable_id("pred", payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "prediction_id": self.prediction_id,
            "instrument": self.instrument,
            "cutoff_date": self.cutoff_date,
            "horizon_trading_days": self.horizon_trading_days,
            "direction": self.direction,
            "confidence": self.confidence,
            "strategy_id": self.strategy_id,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class OutcomeIR:
    prediction_id: str
    start_date: str
    end_date: str
    start_close: float
    end_close: float
    return_pct: float
    actual_direction: str
    max_favorable_excursion_pct: float
    max_adverse_excursion_pct: float
    schema: str = "agentos.market-outcome/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "prediction_id": self.prediction_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "start_close": self.start_close,
            "end_close": self.end_close,
            "return_pct": self.return_pct,
            "actual_direction": self.actual_direction,
            "max_favorable_excursion_pct": self.max_favorable_excursion_pct,
            "max_adverse_excursion_pct": self.max_adverse_excursion_pct,
        }


@dataclass(frozen=True)
class EvaluationIR:
    prediction_id: str
    direction_correct: bool | None
    brier_score: float | None
    signed_score: float | None
    classification: str
    schema: str = "agentos.market-evaluation/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "prediction_id": self.prediction_id,
            "direction_correct": self.direction_correct,
            "brier_score": self.brier_score,
            "signed_score": self.signed_score,
            "classification": self.classification,
        }


@dataclass(frozen=True)
class ReviewIR:
    prediction_id: str
    result: str
    observations: tuple[str, ...]
    lesson_candidates: tuple[str, ...]
    schema: str = "agentos.market-review/v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "prediction_id": self.prediction_id,
            "result": self.result,
            "observations": list(self.observations),
            "lesson_candidates": list(self.lesson_candidates),
        }


Predictor = Callable[[ReplaySnapshot, str, int], PredictionIR]


class MarketReplay:
    def __init__(self, rows: Sequence[Mapping[str, Any]]) -> None:
        ordered = sorted((dict(row) for row in rows), key=lambda row: str(row.get("date") or ""))
        if not ordered:
            raise ValueError("replay requires at least one row")
        instruments = {str(row.get("instrument") or "") for row in ordered}
        if len(instruments) != 1 or "" in instruments:
            raise ValueError("replay rows must belong to exactly one instrument")
        self.instrument = next(iter(instruments))
        self.rows = tuple(ordered)

    def snapshot(self, cutoff_date: str, *, lookback: int | None = None) -> ReplaySnapshot:
        visible = [row for row in self.rows if str(row["date"]) <= cutoff_date]
        if lookback is not None:
            visible = visible[-lookback:]
        if not visible:
            raise ValueError(f"no data available at cutoff {cutoff_date}")
        return ReplaySnapshot(self.instrument, cutoff_date, tuple(visible))

    def run_prediction(
        self,
        *,
        cutoff_date: str,
        horizon_trading_days: int,
        strategy_id: str,
        predictor: Predictor,
        lookback: int | None = None,
    ) -> PredictionIR:
        snapshot = self.snapshot(cutoff_date, lookback=lookback)
        prediction = predictor(snapshot, strategy_id, horizon_trading_days)
        if prediction.instrument != self.instrument:
            raise ValueError("predictor returned wrong instrument")
        if prediction.cutoff_date != cutoff_date:
            raise ValueError("predictor returned wrong cutoff")
        if prediction.horizon_trading_days != horizon_trading_days:
            raise ValueError("predictor returned wrong horizon")
        if prediction.strategy_id != strategy_id:
            raise ValueError("predictor returned wrong strategy")
        return prediction

    def reveal(self, prediction: PredictionIR) -> OutcomeIR:
        dates = [str(row["date"]) for row in self.rows]
        try:
            cutoff_index = max(i for i, value in enumerate(dates) if value <= prediction.cutoff_date)
        except ValueError as exc:
            raise ValueError("prediction cutoff precedes available data") from exc

        target_index = cutoff_index + prediction.horizon_trading_days
        if target_index >= len(self.rows):
            raise ValueError("outcome not yet available for requested horizon")

        start = self.rows[cutoff_index]
        future = self.rows[cutoff_index + 1 : target_index + 1]
        end = self.rows[target_index]
        start_close = float(start["close"])
        end_close = float(end["close"])
        return_pct = (end_close / start_close - 1.0) * 100.0

        highs = [float(row["high"]) for row in future if row.get("high") is not None]
        lows = [float(row["low"]) for row in future if row.get("low") is not None]
        mfe = ((max(highs) / start_close) - 1.0) * 100.0 if highs else return_pct
        mae = ((min(lows) / start_close) - 1.0) * 100.0 if lows else return_pct

        return OutcomeIR(
            prediction_id=prediction.prediction_id,
            start_date=str(start["date"]),
            end_date=str(end["date"]),
            start_close=start_close,
            end_close=end_close,
            return_pct=return_pct,
            actual_direction=_direction(return_pct),
            max_favorable_excursion_pct=mfe,
            max_adverse_excursion_pct=mae,
        )

    @staticmethod
    def evaluate(prediction: PredictionIR, outcome: OutcomeIR) -> EvaluationIR:
        if prediction.direction == "ABSTAIN":
            return EvaluationIR(
                prediction_id=prediction.prediction_id,
                direction_correct=None,
                brier_score=None,
                signed_score=None,
                classification="ABSTAINED",
            )

        correct = prediction.direction == outcome.actual_direction
        if prediction.direction in {"UP", "DOWN"}:
            event = 1.0 if correct else 0.0
            brier = (float(prediction.confidence) - event) ** 2
            signed = float(prediction.confidence) if correct else -float(prediction.confidence)
        else:
            brier = 0.0 if correct else 1.0
            signed = 1.0 if correct else -1.0

        return EvaluationIR(
            prediction_id=prediction.prediction_id,
            direction_correct=correct,
            brier_score=brier,
            signed_score=signed,
            classification="CORRECT" if correct else "WRONG",
        )

    @staticmethod
    def review(prediction: PredictionIR, outcome: OutcomeIR, evaluation: EvaluationIR) -> ReviewIR:
        observations = (
            f"predicted={prediction.direction} actual={outcome.actual_direction}",
            f"return_pct={outcome.return_pct:.4f}",
            f"confidence={prediction.confidence:.4f}",
        )
        lessons: tuple[str, ...]
        if evaluation.classification == "WRONG":
            lessons = (
                "Inspect missing features, regime mismatch, and pattern misclassification before proposing a strategy delta.",
            )
        elif evaluation.classification == "CORRECT":
            lessons = (
                "Treat this as supporting evidence only; require repeated out-of-sample reuse before promotion.",
            )
        else:
            lessons = ("No directional lesson from an abstained prediction.",)
        return ReviewIR(
            prediction_id=prediction.prediction_id,
            result=evaluation.classification,
            observations=observations,
            lesson_candidates=lessons,
        )
