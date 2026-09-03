# ONE Experience IR

Status: Core implementation slice for Issue #117. This document does **not** promote general Cognitive IR from Research.

## Decision

ONE Experience is a governed projection/artifact layer over canonical state and accepted evidence. It is not a fourth authority store.

The reusable lesson itself is represented as **Experience IR** (`agentos.experience-ir/v1`). A prose summary is optional display metadata only. Executors hydrate IR, provenance references, semantic digests, and expected benchmark dimensions; they do not depend on a required natural-language summary.

This distinction is intentional:

- Canonical IR (`agentos.ir/v1`) represents current project continuation/state.
- Experience IR (`agentos.experience-ir/v1`) represents reusable learned constraints, procedures, heuristics, decisions, failure patterns, or benchmark patterns.
- Experience IR is **not** claimed to be a universal/model-cognitive IR.
- Accepted evidence and existing governance remain authoritative. A Node/executor may propose Experience but may not self-authorize acceptance.

## Artifact chain

1. **Extraction proposal** (`agentos.experience-extraction/v1`)
   - identifies origin node/surface/executor/backend where trustworthy;
   - references canonical source evidence;
   - records what facts were generalized and what was excluded;
   - carries a candidate governed Experience artifact;
   - candidate authority must remain `candidate`.

2. **Governed Experience artifact** (`agentos.experience/v1`)
   - has stable `experience_id`, project/scope, kind, IR, provenance, authority, and validity;
   - may have `display.summary`, but display text is non-authoritative and excluded from the semantic digest.

3. **Hydration projection** (`agentos.experience-hydration/v1`)
   - includes exact Experience IDs;
   - includes each semantic IR and semantic digest;
   - maps each Experience item to the behavior dimensions it is expected to influence;
   - has a stable projection digest.

4. **Behavior delta report** (`agentos.experience-behavior-delta/v1`)
   - stores baseline/hydrated parsed value and pass state per dimension;
   - classifies `improved`, `unchanged-correct`, `unchanged-wrong`, or `regressed`;
   - lists candidate Experience IDs, without claiming item-level causality.

5. **Attribution report** (`agentos.experience-attribution/v1`)
   - consumes B-minus-Ei ablation runs;
   - emits an `experience_id × behavior_dimension` matrix;
   - a single ablation can yield `supported`, `ambiguous`, `no-observed-effect`, or `negative`;
   - this layer deliberately does not emit `direct` from one stochastic ablation.

## Experience IR v1

An Experience IR contains:

- `nodes`: typed semantic operations;
- `entrypoints`: the semantic units to project;
- `expected_behavior_dimensions`: benchmark dimensions that should be observable if the lesson is inherited.

Each node has:

- stable local `id`;
- `op`: `assert | require | forbid | prefer | avoid | invoke | match | set`;
- semantic `predicate`;
- typed `arguments` and optional typed `value`.

This makes an Experience item independently selectable and removable for ablation. The unit of regression is therefore the stable `experience_id`, not a paragraph of prompt text.

## Hash semantics

`experience_semantic_digest()` excludes optional human `display` metadata. Changing wording must not create the illusion of a new learned behavior. Changing IR, scope, kind, validity, project, or identity changes the semantic digest.

The hydration digest is computed over the exact semantic projection delivered to the executor.

## Authority and safety invariants

- only `accepted` Experience may hydrate;
- superseded or invalidated Experience is not discovered;
- Experience availability never grants mutation/execution/publication authority;
- candidate extraction cannot self-authorize acceptance;
- credential-like keys are rejected recursively from Experience IR/artifacts/proposals;
- runtime accepted Experience remains ONE-owned data, seeded idempotently and refusing implicit overwrite.

## #117 promotion boundary

This slice provides the contract needed for observable extraction, hydration manifests, before/after diffs, and bounded ablation attribution. It does **not** by itself prove the Master Experience Floor.

Issue #117 remains open until a real fresh executor run persists:

- A: no Experience;
- B: full accepted Experience IR set;
- B-minus-Ei/group ablations for material lessons;
- per-dimension delta;
- bounded attribution;
- privacy/authority checks;
- repeatability evidence where stochasticity matters.
