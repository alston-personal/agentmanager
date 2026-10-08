# Growth Observation Hook

## Goal

Turn Growth Proof capture from an optional side-channel into a normal part of verified work completion.

## Flow

```text
executor uses prior validated experience
  -> attach growth context to durable work item
  -> executor/inspector completes acceptance
  -> work_completion transitions to done
  -> common completion seam emits growth observation
  -> $AGENT_DATA_ROOT/growth-proof/inbox.jsonl
  -> Growth Auditor timer consumes new observation
  -> Growth Proof Ledger
```

Executors do not write the Growth Auditor ledger directly.

## Failure isolation

Growth Proof is an observer of task completion. If the observer cannot write its inbox, verified completion remains authoritative. The work history records `growth_observation_failed` so the monitoring layer can repair/replay the evidence path without reopening an already verified task.

## Attaching context

Use the durable completion controller:

```bash
python3 scripts/work_completion.py attach-growth \
  --id <work-id> \
  --actor <executor-or-controller> \
  --input growth-context.json
```

Minimum useful context:

```json
{
  "source_experience": ["wardrobe-runtime:v1"],
  "candidate_id": "runtime-session-pattern",
  "independent_reuse": true,
  "reuse_boundary": "cross-executor"
}
```

For G3/G4 claims, include controlled before/after metrics. A completion receipt is automatically added to the observation evidence when the item reaches verified `done`.

## Responsibility

The common hook removes the need for every executor to understand Growth Auditor storage. Executors only declare which validated prior experience they reused. Completion owns emission; Growth Auditor owns proof classification and ledgering.
