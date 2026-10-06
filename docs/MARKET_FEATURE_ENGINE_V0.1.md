# Market Feature Engine v0.1

Parent: #1200 / #1249 / #1250 / #1251

## Purpose

Turn only replay-visible observations into a bounded feature frame consumable by Strategy Delta masters.

## v0.1 features

Bar-only:
- `price_action`: bounded log return over up to 5 visible observations
- `volume`: bounded latest-volume expansion/contraction relative to prior visible observations
- `market_regime`: bounded recent return proxy

Not fabricated when unavailable:
- `foreign_flow`
- `margin`
- `ownership_distribution`

Missing features are explicitly listed in `agentos.market-feature-frame/v1`.

## Important limitation

This is a plumbing/reference feature engine, not a validated behavioral model.

The real behavioral research begins when official flow, margin, lending, TDCC ownership distribution, and market-index context are added and Replay Tournament measures out-of-sample behavior.

## CLI path

```
historical loader JSONL
  -> market_replay_tournament.py
  -> ReplaySnapshot
  -> FeatureFrame
  -> four seed masters
  -> Prediction/Outcome/Evaluation/Review
```

This completes the minimum end-to-end offline loop without public posting or real trading.
