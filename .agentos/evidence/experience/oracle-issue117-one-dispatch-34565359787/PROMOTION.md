# Issue #117 — Oracle ONE Experience final promotion evidence

Status: `MASTER_EXPERIENCE_FLOOR=VERIFIED` for the bounded Oracle Codex / AgentOS Core #117 benchmark.

This marker is deliberately scoped. It does **not** claim arbitrary cross-model cognitive-state portability, hidden-state portability, or universal executor equivalence.

## Live path

- Workflow: `Oracle Exact Generation Executor Job Rollout` run `34565359787` (#34)
- Source ref: `core/integration`
- Exact source commit: `189c227fd67b00c9481a8a6549c058553bd882e6`
- Artifact id: `10185822214`
- Artifact digest: `sha256:7a4df1d6b2c33cf1d3408edcbb9b7550927cf6923644e909a86d8f1819c6bdfe`
- ONE controller entered: `true`
- Node: `oracle-core-node`
- Job type: `experience.regression`
- Executor class: `openai-codex-local`
- `executor_available=true`
- `routable=true`
- `authorized=true`
- `successful=true`
- `credential_exposed=false`

## A/B result

- baseline: `6/7 = 0.8571428571428571`
- ONE-hydrated: `7/7 = 1.0`
- uplift: `+1/7 = 0.1428571428571429`
- hydration receipt: PASS
- regression classification: `EXPERIENCE_REGRESSION_PASS`
- regressed dimensions: none

The only improved benchmark dimension was:

- `canonical_development_branch`: baseline `null` / FAIL -> hydrated `core/integration` / PASS

The exact hydration manifest was recorded in `agentos.experience-attribution-evidence/v2`, including these accepted Experience IDs:

- `core.branch-authority.v2`
- `core.evidence-scope-and-capability-semantics.v2`
- `core.node-executor-boundary.v1`
- `core.discover-before-reinvent.v2`
- `core.protected-main-human-authority.v1`
- `core.workspace-not-continuation-authority.v1`

Hydration projection digest:
`e02f6036b9aaf6a6e4a461d19d7395d15b54504648a1fcd7ebc320b1355bf17a`

## Controlled attribution / ablation

The material improvement had one directly matching Experience item: `core.branch-authority.v2`. A fixed provider-owned B-minus-Ei counterfactual therefore withheld only that item while retaining the other five accepted Experience items. The accepted store and Canonical IR were not mutated.

Three fresh Codex repeats produced:

1. `canonical_development_branch = "main"` -> FAIL
2. `canonical_development_branch = null` -> FAIL
3. `canonical_development_branch = "main"` -> FAIL

Result:

- effect: `lost-improvement`
- attribution confidence: `supported`
- repeat count: `3`
- target passes: `[false, false, false]`
- withheld Experience: `core.branch-authority.v2`
- target dimension: `canonical_development_branch`

This is bounded supporting attribution, not an overclaim of deterministic causal identity for all LLM behavior.

## Promotion-gate mapping

The revised #117 promotion gate is satisfied for this benchmark:

- observable Experience artifacts with provenance/scope/governance: present in the accepted Experience set/seed;
- exact hydration manifest: persisted in the v2 attribution receipt;
- per-dimension before/after values and pass state: persisted;
- regression detection: all seven dimensions recorded, no regression observed;
- bounded attribution/ablation for the material improvement: 3/3 B-minus-`core.branch-authority.v2` lost the improvement, confidence `supported`;
- fresh executor path through ONE rather than conversation replay: live workflow entered ONE controller and bounded executor job;
- privacy/authority boundary: `credential_exposed=false`, and executor availability/routability/authorization/success remain separately evidenced.

## Non-claims

- General Cognitive IR remains Research.
- This evidence does not certify every backend/model/surface or `vopc5750`.
- Node online status remains distinct from executor availability.
- Protected `main` publication authority remains separate and is not granted by this promotion.
