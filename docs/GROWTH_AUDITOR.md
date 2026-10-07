# AgentOS Growth Auditor

## Purpose

The Growth Auditor is the fixed owner for collecting evidence that AgentOS becomes measurably better because of accumulated validated experience.

It does **not** execute the product task and it does **not** decide user intent. It observes execution/acceptance receipts and reusable-experience signals, then records attributable Growth Proof evidence.

## Responsibility boundary

- **Executor** — performs work.
- **Closure Owner / Atlast** — keeps an open goal moving through execution -> acceptance -> close -> next work.
- **Growth Auditor** — asks whether prior validated experience caused later independent execution to improve.

The Growth Auditor must not count persistence, larger context, one-off fixes, or model upgrades as self-growth.

## Runtime contract

Runtimes may emit JSONL observations containing:

```json
{
  "source_experience": ["wardrobe-runtime:v1"],
  "new_task": "participant runtime integration",
  "candidate_id": "runtime-session-pattern",
  "transferred_pattern": ["session isolation", "persistent job state", "receipt completion"],
  "independent_reuse": true,
  "reuse_boundary": "cross-executor",
  "controlled_variables": {
    "model": "fixed",
    "toolset": "fixed"
  },
  "metrics_before": {
    "human_interventions": 4,
    "iterations": 12
  },
  "metrics_after": {
    "human_interventions": 1,
    "iterations": 4
  },
  "evidence": [
    "receipt://before",
    "receipt://after"
  ]
}
```

Run:

```bash
python3 scripts/growth_auditor_tick.py \
  --input /path/to/growth-observations.jsonl \
  --receipt-out /path/to/growth-auditor-receipt.json
```

The persistent ledger is stored under:

```text
$AGENT_DATA_ROOT/growth-proof/ledger.json
```

Mutable evidence therefore remains in the data layer, not the logic repository.

## Classification

The automatic classifier is intentionally conservative:

- no source experience -> not qualified;
- source only -> G0;
- reusable candidate/pattern exists -> G1;
- later independent reuse -> G2;
- measured before/after uplift -> G3;
- measured uplift across executor/node/model/session boundary -> G4;
- G5 remains a longitudinal claim and should be produced by an aggregate benchmark rather than inferred from one observation.

Explicit verdicts are accepted only when they are one of G0-G5.

## Operating rule

Every reusable-experience-aware runtime SHOULD emit an observation after acceptance. A scheduler/monitor may run the Growth Auditor periodically, but the auditor's semantics are event-driven: it processes newly emitted evidence and deduplicates repeated proof records.

The auditor must remain skeptical. A candidate is not a Growth Proof until later reuse and measurement justify the level claimed.
