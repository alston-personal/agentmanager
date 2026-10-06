# Market Replay / Time Machine v0.1

Parent: #1200 / #1250

## Objective

Replay historical market states without future leakage, commit an immutable prediction artifact, advance by trading-day horizon, reveal the outcome, evaluate it, and create a review/lesson candidate.

## Contract

```
Historical bars
  -> cutoff date
  -> ReplaySnapshot (<= cutoff only)
  -> predictor
  -> Prediction IR
  -> advance N trading days
  -> Outcome IR
  -> Evaluation IR
  -> Review IR
```

## Safety invariant

The predictor receives only a `ReplaySnapshot`. Construction fails if any row exceeds the cutoff date.

Prediction identity is content-addressed from:
- instrument
- cutoff
- horizon
- direction
- confidence
- strategy
- evidence

The outcome is never embedded in the prediction artifact.

## Current scoring

v0.1 records:
- direction correctness
- Brier score for UP/DOWN probability confidence
- signed confidence score
- realized return
- MFE
- MAE

This is intentionally minimal. Portfolio PnL and trading-cost simulation belong to a later paper-trading stage.

## Review rule

A single correct or wrong result can only generate a lesson candidate. It cannot directly promote a Strategy Delta.

## Next slice

Connect:
1. normalized TWSE history from #1256,
2. resolved Strategy Delta instances from #1257,
3. a Replay Tournament that evaluates all seed masters at the exact same cutoff dates.
