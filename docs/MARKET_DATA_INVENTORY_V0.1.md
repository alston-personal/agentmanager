# Market Data Inventory v0.1

Project: `market-master-evolution`
Parent: #1200 / #1249

## Goal

Build a replayable historical dataset without future leakage. Raw source responses are immutable; normalized and derived data can always be rebuilt.

## Source policy

### TWSE price/volume

Current whole-market OpenAPI `/v1/exchangeReport/STOCK_DAY_ALL` is suitable for daily forward collection but is not the historical backfill mechanism.

Historical backfill v0.1 uses the TWSE RWD monthly endpoint:

`/rwd/zh/afterTrading/STOCK_DAY?date=YYYYMM01&stockNo=NNNN&response=json`

The loader stores the original response before normalization.

### TDCC ownership distribution

Target for v0.2. Weekly holder-distribution snapshots are valuable for population migration signals. Adapter must preserve publication date and effective balance date separately.

### TAIFEX institutional positioning

Target for v0.2. Public query history is limited; older history may require official data purchase. The archive must therefore collect forward daily snapshots even before deep historical backfill is purchased.

## Initial universe

- 2330
- 2454
- 2317
- 2382
- 3231
- TAIEX (separate adapter)

## Storage contract

```
market-data/
  raw/
    <source>/<instrument>/<request-key>.json
    <source>/<instrument>/<request-key>.receipt.json
  normalized/
    <source>/<instrument>.jsonl
```

Raw files are immutable. If the same source/request key later returns different bytes, the loader raises a conflict instead of silently overwriting history.

## Replay safety

- normalization contains only fields present in the source response
- no forward returns are stored in the market-bar row
- outcomes belong in separate Outcome IR produced only after replay advances
- missing values stay missing; no silent interpolation
- corporate actions require a later explicit adjustment layer, never mutation of raw data

## v0.1 acceptance

1. Fetch at least one historical month for 2454.
2. Persist immutable raw response and receipt.
3. Normalize daily bars.
4. Repeat the same request without changing raw history.
5. Deliberately alter a fixture and prove immutable-conflict detection.
