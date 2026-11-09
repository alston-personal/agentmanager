# AgentOS Growth Auditor Contract

## Purpose

The **Growth Auditor** is the fixed responsibility for collecting evidence that AgentOS becomes measurably better because of accumulated validated experience.

It does **not** execute the product task and it does **not** decide user intent. It observes execution/acceptance receipts and reusable-experience signals, then records attributable Growth Proof evidence.

## Responsibility Boundary

- **Executor** — performs work.
- **Closure Owner / Atlast** — keeps an open goal moving through execution -> acceptance -> close -> next work.
- **Growth Auditor** — asks whether prior validated experience caused later independent execution to improve.

The Growth Auditor must not count persistence, larger context, one-off fixes, or model upgrades as self-growth.

## Five-Tier Growth Classification (G0 - G5)

The Growth Auditor evaluates claims conservatively:

- **G0 (No Qualification / Source Only)**:
  - Historical interactions, transcripts, or session logs are recorded. Persistence alone is not self-growth.
- **G1 (Reusable Pattern)**:
  - Reusable candidate/pattern exists and is extracted.
- **G2 (Independent Later Reuse)**:
  - A subsequent session or executor retrieves and successfully applies previously stored validated patterns.
- **G3 (Causal Before-vs-After Uplift)**:
  - Measured latency reduction, token reduction, or test pass-rate improvement directly attributable to validated experience.
- **G4 (Cross-Boundary Measured Transfer)**:
  - Experience gained in one project, model, or executor transfers to an independent project or executor with measurable performance gain.
- **G5 (Longitudinal Autonomous Evolution)**:
  - Sustained multi-cycle capability expansion without human prompting or regression. Longitudinal proofs must not be inferred from a single event.

## Runtime Contract

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
