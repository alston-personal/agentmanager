# Longitudinal Cognitive Continuity Benchmark (LCCB)

Status: experimental research protocol. It is descriptive/evaluative and grants no AgentOS authority.

## Research question

With base-model weights and decoding policy held fixed, does accumulated AgentOS experience plus structured memory, relations, reconciliation, lifecycle management and governance produce measurable improvement on held-out tasks over time?

The benchmark deliberately avoids equating graph size with intelligence. It measures task-relevant recall, provenance, stale-belief avoidance, continuity and governance behavior.

## Experimental invariance

Within one longitudinal series, freeze:

- model/provider version;
- decoding policy;
- tool policy;
- enabled cognitive modules;
- capability manifest;
- governance profile;
- evaluator/rubric.

Only accumulated experience, memory state, relations, synthesis products and lifecycle state may change. Any capability/model/governance configuration change starts a new series.

Recommended controlled stages are `age-0`, `age-100`, and `age-1000`.

## Benchmark categories

1. **Recall** — retrieve durable facts and their provenance.
2. **Supersession** — prefer current knowledge over stale/superseded beliefs.
3. **Revival** — recover relevant Cold/Archive knowledge when explicitly/strongly triggered.
4. **Transfer** — reuse a validated structural principle in a held-out domain without inventing unsupported relations.
5. **Continuity** — resume work after session/model/runtime changes with minimal lost constraints or duplicated work.
6. **Governance** — resurface important work without fabricating authority; reject unauthorized effects; preserve audit/approval boundaries.

## Core metrics

The deterministic scorer records:

- fact recall accuracy;
- source/provenance recall accuracy;
- stale fact error rate;
- unauthorized action attempt rate;
- task completion rate.

Additional paper metrics may be computed from raw observations, but definitions must be versioned and reported.

## Controlled Synthetic Track

Project Meridian is a deterministic fixed-seed evolving world with 1,000 ordered `ExperienceEvent`s. It mixes durable facts, procedures, work state and governance modes with non-durable background events, and later emits explicit revisions so stale values remain present in history.

The same task keys are evaluated at age 0, 100 and 1,000. Age 0 expects `unknown`; later ages require the current state.

Frozen packs are physically separated:

```text
public/experience.jsonl   # model-visible history
public/tasks.jsonl        # model-visible prompts only
private/labels.jsonl      # evaluator-only expected/forbidden facts
manifest.json             # dataset identity/hashes
```

The model runner must never open `private/labels.jsonl`.

Build with:

```bash
python scripts/build_lccb_synthetic_pack.py \
  --output-dir artifacts/lccb-pack \
  --seed 73129 \
  --events 1000
```

## Fixed-model execution

A provider-neutral runtime contract records raw task artifacts. For direct controlled experiments, an OpenAI-compatible research runner is also provided:

```bash
export LCCB_BASE_URL='https://provider.example/v1'
export LCCB_API_KEY='...'
export LCCB_MODEL='immutable-model-version'

python scripts/run_lccb_openai_compatible.py \
  --pack artifacts/lccb-pack \
  --output artifacts/raw-responses.jsonl \
  --stages 0,100,1000 \
  --temperature 0 \
  --repeat 3
```

The runner reads only public artifacts, makes one batched model request per cognitive age/repeat, and emits task-level prompt/response hashes. The API key is read only from the environment and is never written to output.

## Independent scoring

Only the evaluator opens private labels:

```bash
python scripts/score_lccb_responses.py \
  --pack artifacts/lccb-pack \
  --responses artifacts/raw-responses.jsonl \
  --output artifacts/scored-results.json
```

## Deterministic sanity baselines

CI produces three controlled baselines as a benchmark-sensitivity check, not as an AgentOS efficacy claim:

- `always_unknown`: no retained experience;
- `first_observed`: retains earliest matching state and never supersedes it;
- `latest_structured`: deterministically tracks latest structured state.

At age 1,000 on seed 73129, the CI-generated artifact reports:

```text
always_unknown      recall 0.0000   stale 0.0000
first_observed      recall 0.4615   stale 0.5385
latest_structured   recall 1.0000   stale 0.0000
```

This verifies that the controlled track distinguishes mere retention from update-aware state maintenance.

## Required comparisons for the paper

### A. Fixed-model aging

Same model/version/policy at every stage. Compare frozen base-model/no-persistent-cognition against AgentOS at age 0 / 100 / 1,000.

### B. Cross-model continuity

Perform a multi-step task across at least two replaceable model/runtime bodies while preserving the same Project/Realm cognition. Measure lost constraints, duplicate work, stale assumptions, resume latency and final task correctness.

### C. Ablation

At minimum compare Full AgentOS against removal/disablement of:

- retrieval-only/no supersession;
- reconciliation;
- relational association;
- adaptive lifecycle/revival;
- governance gating.

Ablations must not silently change unrelated policies.

### D. Governance adversarial cases

Include cases where urgency/importance is high but authority is absent. The correct outcome is resurfacing/proposal, not execution. Include under-declared effects, unknown capabilities, stale approvals and idempotency collisions.

## Cognitive Observatory

`agentos.cognitive-observatory/v1` captures content-addressed descriptive snapshots and `agentos.cognitive-delta/v1` records lineage/diffs. Observatory output is never ProjectState, confidence authority or governance authority. Observing cognition must not change cognition.

## Leakage controls

- Held-out benchmark labels must not be inserted into experience streams before evaluation.
- Model execution reads only `public/` artifacts.
- Expected answers, forbidden facts and private evidence labels remain evaluator-only.
- Evaluator version must be logged separately from model prompts.
- Repeated evaluation must distinguish test exposure from genuine accumulated experience.

## Evidence preservation

Preserve dataset manifest, public pack, raw responses, scored results, exact git commit, model condition, evaluator version, repeat/seed data, and relevant Cognitive Observatory snapshot/delta references.

## Reporting rule

Never report planned benchmark values as empirical results. Deterministic unit/regression tests validate implementation invariants; they are not evidence of longitudinal cognitive improvement. Model-based longitudinal results require actual benchmark runs with preserved manifests and raw observations.
