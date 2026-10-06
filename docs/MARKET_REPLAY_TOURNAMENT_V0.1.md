# Market Replay Tournament v0.1

Parent: #1200, #1250, #1251

## Purpose

Compare multiple Strategy Delta-derived Market Masters under exactly the same historical information boundary.

A tournament round guarantees:
- identical instrument
- identical cutoff
- identical horizon
- identical feature frame
- identical realized outcome
- different strategy weights/deltas only

This isolates whether a Strategy Delta actually changes decision behavior.

## v0.1 predictor

The tournament uses a deliberately simple weighted-feature predictor. It is not a claim of market edge.

```
normalized_score =
  sum(feature_value * strategy_weight)
  / sum(abs(strategy_weight))
```

Direction and confidence are derived deterministically from that score.

The important property is replaceability: a future Feature Engine or prediction model can replace this function without changing Replay, Prediction IR, Outcome IR, Evaluation IR, or Tournament contracts.

## Disagreement is data

If Flow says DOWN and Momentum says UP at the same cutoff, the disagreement is retained rather than averaged away. Later work can learn which master wins under which market regime.

## Promotion boundary

Tournament performance is evidence, not automatic authority. A Strategy Delta remains a candidate until validation, locked holdout, later reuse, and measured uplift satisfy the Cognitive Growth Protocol.
