# TWSE T86 Institutional Flow Adapter v0.1

Parent: #1249 / #1200

## Why

The first real 2454 replay smoke test showed that Flow, Momentum, Reversal and Neutral masters mostly produced the same direction because only bar-derived features were available.

This adapter adds the first genuinely different behavioral input: official TWSE three-major-institution daily flow.

## Source

TWSE T86 daily report. The public TWSE page states that this report is available from 2012-05-02 onward.

## Replay boundary

The normalized row records an EOD availability time and is only merged into bars for the same trading date. Current replay semantics are end-of-day decisions for subsequent trading days.

No future T86 row may be visible before its date/cutoff.

## Derived feature

`foreign_flow` is a bounded ratio of recent foreign net shares to recent traded volume.

This is a reference normalization, not a validated alpha formula.

## CLI

```
python3 scripts/market_t86_loader.py \
  --bars market-data/normalized/twse-stock-day/2454.jsonl \
  --stock 2454
```

The CLI derives trading dates from existing market bars, so it does not probe weekends or holidays unnecessarily.

## Next acceptance

Re-run the same 2454 replay window with and without T86 input and verify:
1. `foreign_flow` is present only when source data exists.
2. Flow Master predictions diverge from at least one other seed strategy in some rounds.
3. Any apparent performance difference is treated as evidence to validate, not as edge.
