---
name: cognitive_growth
description: Turns validated experience into reusable, versioned capability improvements without modifying model weights.
---
# Cognitive Growth Protocol

AgentOS cognitive growth is **not** the claim that an underlying LLM's weights are being trained during normal use. It is the system-level process by which repeated experience becomes reusable capability that survives executor/model/session changes.

## Definition

A system has demonstrated cognitive growth only when all of the following occur:

```text
Experience
  -> Extract reusable candidate
  -> Validate candidate against evidence/tests
  -> Promote into canonical knowledge/skill/rule/IR transform
  -> Load it in a later independent execution
  -> Measure improved outcome versus the prior baseline
```

Memory alone is not growth. A larger transcript, summary, vector store, or context window only improves recall. Growth requires a **validated reusable delta** plus evidence that a later executor benefits from it.

## Growth Units

A promoted cognitive delta MAY be one of:
- operating rule / invariant
- reusable skill or workflow
- domain IR schema or transform
- failure signature + recovery routine
- tool-selection policy
- validated architectural pattern
- benchmark-derived heuristic with stated confidence and scope

Each promoted unit SHOULD include:

```yaml
id: <stable-id>
revision: <monotonic integer>
kind: rule|skill|pattern|transform|recovery|heuristic
source_experience: <receipt/commit/session reference>
claim: <what capability improves>
scope: <where claim is valid>
validation: <tests/evidence>
confidence: 0.0-1.0
supersedes: []
rollback: <how to disable/revert>
```

## Promotion Gates

1. **Novelty** — candidate is not merely duplicate memory.
2. **Generalization** — candidate is reusable beyond the exact triggering instance.
3. **Evidence** — at least one reproducible test/receipt supports it.
4. **Safety/Governance** — it does not weaken immutable governance or newer user intent.
5. **Versioning** — promotion is monotonic and reversible.
6. **Reuse** — a later executor can discover/load it without the original conversation.
7. **Uplift** — where measurable, later performance is compared against a prior baseline.

If gates 1-5 pass but reuse/uplift have not yet been observed, label the unit `validated_candidate`, not `demonstrated_growth`.

## Relationship to Triple-Layer Memory

Triple-layer memory provides:
- Identity: who/constraints
- Context: what is happening
- Knowledge: facts and reusable artifacts

Cognitive growth is the **write/promotion loop** across those layers. It decides which experience is worthy of becoming durable Knowledge or an operating Skill/Rule and requires later reuse evidence.

## Relationship to Continuation

Context compaction is not cognitive growth. It is a representation optimization and must obey User Intent Monotonicity.

A continuation failure MAY, however, become a growth event when:
1. the failure is diagnosed,
2. a general invariant/recovery routine is extracted,
3. it is validated with a regression test,
4. the rule is promoted,
5. a future continuation avoids the same failure.

## Required Metrics

Track at minimum:
- `promoted_units_total`
- `validated_candidates_total`
- `reuse_hits_total`
- `reuse_success_rate`
- `regressions_prevented_total`
- `cross_executor_transfer_success_rate`
- task-specific quality/time/cost deltas when available

## Current Interpretation

Do not say "the model learned" unless weights/training actually changed. Prefer:

> "AgentOS accumulated a validated reusable capability delta that later executors can load."

Only call that delta **demonstrated cognitive growth** after later independent reuse produces evidence of improved behavior.
