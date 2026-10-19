# AgentOS Growth Proof

## Status

**Highest principle.**

AgentOS must be able to prove that accumulated, validated experience causes later independent executions to perform better. This is stronger than memory, persistence, continuity, retrieval, logging, or one-off repair.

The preferred claim is:

> AgentOS accumulated a reusable capability delta that survived the original session/executor and produced measurable uplift in a later execution.

Do not claim demonstrated self-growth unless the evidence reaches the required proof level below.

## Core hypothesis

Holding relevant confounders constant, an AgentOS instance with validated accumulated experience should outperform an otherwise equivalent cold/baseline AgentOS instance.

```text
same model/provider/version
same tool set
same permissions
same task/evaluation
same hardware class where relevant

cold AgentOS  <  experienced AgentOS
```

The strongest tests additionally show that the improvement transfers across executor, node, or model boundaries.

## What does NOT count as Growth Proof

The following are useful infrastructure but are insufficient on their own:

- a larger prompt, transcript, vector store, or memory database;
- persistence across restart;
- successful context continuation;
- a manually coded fix;
- a regression test that only proves the fix exists;
- a candidate rule that has never been independently reused;
- better results after changing the underlying model/provider;
- a successful task with no comparable baseline;
- metrics collection without evidence that accumulated experience changed later behavior.

## Proof ladder

### G0 — Persistence

Experience can be stored and recovered.

Evidence: persistence/retrieval tests.

Interpretation: prerequisite only; no growth claim.

### G1 — Candidate extraction

A reusable rule/skill/pattern/recovery/IR delta is extracted from a real experience and given scope, evidence, confidence, version, and rollback semantics.

Interpretation: learning candidate, not demonstrated growth.

### G2 — Independent reuse

A later execution that did not depend on the original conversation discovers/loads the delta and uses it successfully.

Interpretation: reusable accumulated competence exists.

### G3 — Counterfactual uplift

The same or equivalent task is evaluated with and without the accumulated delta. The experienced path measurably improves one or more accepted outcomes without unacceptable regression.

Preferred metrics:

- task success rate;
- human intervention rate;
- recovery time;
- steps/actions;
- quality/accuracy;
- latency;
- cost per successful task;
- regression rate.

Interpretation: minimum level for a strong **AgentOS Growth Proof** claim.

### G4 — Cross-boundary transfer

A validated delta learned on one model, executor, session, or node produces uplift on another.

Interpretation: strong evidence that competence lives in AgentOS rather than only in a particular model/session.

### G5 — Longitudinal autonomous growth

Across a growing task history, AgentOS repeatedly extracts, validates, promotes, reuses, supersedes/rolls back, and measures deltas so that an age curve emerges.

Example:

```text
Age 0   -> baseline
Age 100 -> measurable uplift
Age 1000 -> further uplift without unacceptable regression
```

Interpretation: strongest form of the product thesis.

## Causal proof protocol

For each candidate proof:

1. identify the triggering experience and immutable evidence/receipt;
2. extract the smallest reusable delta;
3. define claim, scope, confidence, supersession and rollback;
4. validate the delta against a regression set;
5. freeze or record major confounders;
6. execute a later independent task with the delta available;
7. where feasible replay an equivalent task without the delta;
8. compute uplift and regression metrics;
9. record whether reuse crossed session/model/executor/node boundaries;
10. promote only according to the cognitive-growth gates.

Every proof receipt SHOULD identify:

```yaml
proof_id:
candidate_id:
source_experience:
baseline:
experienced:
controlled_variables:
changed_variable: validated cognitive delta
metrics_before:
metrics_after:
uplift:
regressions:
reuse_boundary:
evidence:
verdict: G0|G1|G2|G3|G4|G5
```

## Existing proof seeds in this repository

### 1. Cognitive growth protocol

`.agent/skills/cognitive_growth/SKILL.md` already defines the core chain:

```text
Experience
 -> reusable candidate
 -> validation
 -> promotion
 -> later independent load
 -> measured improvement
```

This is the governing definition, not evidence by itself.

### 2. ProductExperienceStore

`agent_core/product_experience.py` implements versioned experience units, candidate/trusted/canonical states, reuse counters, successful-reuse gating, and regression-prevention metrics.

`tests/test_product_experience.py` proves that a validated candidate cannot be promoted to trusted before successful independent reuse is recorded.

Current proof level: **mechanism support / G1-G2 infrastructure**, not causal uplift.

### 3. GUI demo experience candidates

`.agentos/evidence/gui-demo-product-experience-candidates-20261001.json` contains reusable candidates extracted from a real ChatGPT -> Gemini -> Threads GUI session, including:

- Unicode clipboard input instead of IME-dependent SendKeys;
- semantic URL open instead of typing into the browser address bar;
- clipboard-first media insertion;
- semantic postcondition verification after GUI actions.

The artifact explicitly refuses promotion until later independent reuse demonstrates uplift.

Current proof level: **G1**.

Immediate opportunity: replay equivalent GUI tasks and compare failure/intervention/action counts with each candidate disabled vs enabled.

### 4. OCR human-correction memory

`capabilities/ocr_memory/runtime.py` and `tests/test_ocr_memory.py` demonstrate a particularly strong seed:

- a human correction is stored with template/stamp/entity context;
- repeated confirmation increases trust;
- the correction is later reused during a new extraction;
- the later extraction can replace the prior OCR error and avoid review;
- weak/global context is intentionally prevented from becoming an unsafe global rule.

Current proof level: **G2 in tests, approaching G3**.

Why this matters: this already has the shape of experience -> validated context-specific rule -> later task behavior change.

Missing for G3: an explicit before/after benchmark receipt on held-out real invoices showing quality/intervention uplift with the memory enabled versus disabled.

### 5. Persona growth metrics

`scripts/persona_growth_metrics_collector.py` captures later outcome metrics for posts and writes immutable persona events.

Current proof level: **measurement infrastructure only**.

Missing: connect a promoted strategy delta to later post decisions and compare outcomes against an appropriate baseline. Social metrics are noisy, so this should be supporting evidence rather than the first flagship proof.

### 6. Existing benchmark/regression infrastructure

The repository already contains benchmark and regression surfaces for invoice handwriting, Model2IR, character blueprint and other domains.

These are valuable because Growth Proof should reuse fixed datasets and evaluation logic rather than inventing a bespoke demonstration.

## Priority evidence targets

### P0 — OCR Memory Growth Proof

This should be the first flagship proof because the learning event and later behavioral reuse already exist.

Required experiment:

```text
held-out invoice set
  A: OCR memory disabled
  B: identical pipeline + validated accumulated corrections

compare:
  field accuracy
  invoices requiring review
  false auto-corrections
  latency
```

Acceptance target: measurable reduction in repeated OCR errors/review burden with zero unacceptable false corrections.

Target level: **G3**.

### P0 — GUI Recovery / Rule Reuse Proof

Use the October 1 GUI candidates.

Run equivalent navigation, Chinese input, media attachment, and postcondition tasks with candidate rules disabled/enabled.

Measure:

- task success;
- retries;
- human interventions;
- actions;
- elapsed time;
- wrong-state continuation.

Then run the experienced rules on another compatible executor/node.

Target level: **G3, then G4**.

### P1 — Node onboarding / recurrent incident proof

Historical recurrent failures such as identity assumptions, bootstrap/enrollment, launcher/supervisor readiness, routing and runner ownership should become candidate recovery rules.

The proof is not "we fixed another node." The proof is:

```text
old node required diagnosis/manual repair
 -> generalized invariant/recovery promoted
 -> fresh node encounters equivalent condition
 -> AgentOS prevents or autonomously resolves it
 -> intervention/recovery time drops
```

Target level: **G3/G4**.

### P1 — Provider/executor transfer

Take one already-proven delta and deliberately transfer it across a model/executor boundary while keeping the task comparable.

Target level: **G4**.

## Growth scoreboard

The runtime should ultimately publish an aggregate scoreboard containing at least:

- promoted units;
- validated candidates;
- independent reuse hits;
- reuse success rate;
- regressions prevented;
- cross-executor transfer success rate;
- G3 proof count;
- G4 proof count;
- task success uplift;
- human intervention reduction;
- recovery-time reduction;
- cost/time delta;
- rollback/supersession count.

Counts alone are not sufficient. Preserve links to immutable receipts and benchmark inputs.

## Anti-gaming rules

Growth Proof must not be improved by:

- silently changing the benchmark set;
- changing to a stronger model without accounting for it;
- leaking ground truth into retrieval;
- manually editing the experienced answer for the test;
- counting the same incident repeatedly as independent proof;
- promoting an unsafe broad rule from narrow evidence;
- suppressing negative/regression results;
- measuring only successful survivors.

Negative evidence is part of growth. A candidate that fails a later test should be downgraded, scoped more narrowly, superseded, or rolled back.

## Product gate

New AgentOS architecture should be evaluated against two questions:

1. Does this change help AgentOS execute useful work reliably?
2. Does it preserve or improve our ability to prove that accumulated validated experience makes later execution better?

A feature may still be necessary even when the second answer is no, but architectural work that repeatedly increases complexity without producing execution value or Growth Proof should be challenged.

## Immediate next milestone

Produce the first reproducible **G3** receipt from an existing real workload, preferably OCR memory, then obtain one **G4** cross-executor/node transfer proof.

Until then, the correct claim is:

> AgentOS has implemented substantial cognitive-growth infrastructure and has G1/G2 evidence seeds, but the general self-growth thesis is not yet proven.
