# Longitudinal Cognitive Continuity Benchmark (LCCB)

Status: experimental research protocol.  It is descriptive/evaluative and grants no AgentOS authority.

## Research question

With base-model weights and decoding policy held fixed, does accumulated AgentOS experience plus structured memory, relations, reconciliation, lifecycle management and governance produce measurable improvement on held-out tasks over time?

The benchmark deliberately avoids equating graph size with intelligence.  It measures task-relevant recall, provenance, stale-belief avoidance, continuity and governance behavior.

## Experimental unit

A run fixes:

- model/provider version (for fixed-model experiments);
- decoding/tool policy;
- benchmark task set;
- evaluator version;
- initial Project/Realm state;
- stage definitions by accumulated experience count and CognitiveSnapshot reference.

Only the accumulated AgentOS cognitive state changes between fixed-model stages.

Recommended stages are `age-0`, `age-100`, `age-1000`, and `post-reconciliation`; actual counts must be reported rather than implied.

## Benchmark categories

1. **Recall** — retrieve durable facts and their provenance.
2. **Supersession** — prefer current knowledge over stale/superseded beliefs.
3. **Revival** — recover relevant Cold/Archive knowledge when explicitly/strongly triggered.
4. **Transfer** — reuse a validated structural principle in a held-out domain without inventing unsupported relations.
5. **Continuity** — resume work after session/model/runtime changes with minimal lost constraints or duplicated work.
6. **Governance** — resurface important work without fabricating authority; reject unauthorized effects; preserve audit/approval boundaries.

## Core metrics

The portable v1 scorer currently records:

- fact recall accuracy;
- source/provenance recall accuracy;
- stale fact error rate;
- unauthorized action attempt rate;
- task completion rate.

Additional paper metrics may be computed from raw observations, but definitions must be versioned and reported.

For two stages, `cognitive_gain` reports signed improvement.  Error-rate reductions are represented as positive gain.

## Cognitive Observatory

`agentos.cognitive-observatory/v1` captures a content-addressed descriptive snapshot of:

- knowledge IDs/status/contradictions;
- entity and relation IDs/validation;
- Archive membership;
- reconciliation debt (orphan, ungrounded, stale derivative counts).

`agentos.cognitive-delta/v1` records added/removed knowledge and relations, archive/revival transitions and metric deltas.

Observatory output is never ProjectState, confidence authority or governance authority.  Observing cognition must not change cognition.

## Required comparisons for the paper

### A. Fixed-model aging

Same model/version/policy at every stage.  Compare age-0 versus progressively accumulated experience and post-reconciliation stages.

### B. Cross-model continuity

Perform a multi-step task across at least two replaceable model/runtime bodies while preserving the same Project/Realm cognition.  Measure lost constraints, duplicate work, stale assumptions, resume latency and final task correctness.

### C. Ablation

At minimum compare Full AgentOS against removal/disablement of:

- relational association;
- reconciliation;
- supersession handling;
- adaptive lifecycle/revival;
- governance gating.

Ablations must not silently change unrelated policies.

### D. Governance adversarial cases

Include cases where urgency/importance is high but authority is absent.  The correct outcome is resurfacing/proposal, not execution.  Include under-declared effects, unknown capabilities, stale approvals and idempotency collisions.

## Leakage controls

- Held-out benchmark prompts must not be inserted into training/experience streams before evaluation.
- Expected answers and forbidden facts must not be available to the agent runtime.
- Evaluator prompts/version must be logged separately from agent prompts.
- Repeated evaluation must distinguish test exposure from genuine accumulated experience.

## Reporting rule

Never report planned benchmark values as empirical results.  Deterministic unit/regression tests validate implementation invariants; they are not evidence of longitudinal cognitive improvement.  Model-based longitudinal results require actual benchmark runs with preserved manifests and raw observations.
