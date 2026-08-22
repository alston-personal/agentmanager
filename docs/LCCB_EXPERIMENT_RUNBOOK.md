# LCCB fixed-model experiment runbook

This runbook is research-only. It does not enable AgentOS production authority or external actions.

## 1. Freeze the controlled pack

```bash
python scripts/build_lccb_synthetic_pack.py \
  --output-dir artifacts/lccb-pack \
  --seed 73129 \
  --events 1000
```

The model runner may read only:

- `artifacts/lccb-pack/public/experience.jsonl`
- `artifacts/lccb-pack/public/tasks.jsonl`
- `artifacts/lccb-pack/manifest.json`

It must never read `private/labels.jsonl`.

## 2. Freeze the model condition

Record an immutable provider/model version. Do not use a floating alias when a dated/revision identifier is available.

```bash
export LCCB_BASE_URL='https://provider.example/v1'
export LCCB_API_KEY='...'
export LCCB_MODEL='immutable-model-version'
```

Never commit the API key or write it into artifacts.

For one longitudinal series, keep constant:

- model/version;
- system instruction;
- temperature and decoding parameters;
- tool policy;
- enabled cognitive modules;
- capability manifest;
- governance profile.

Any change begins a new experimental series.

## 3. Run the public benchmark

A deterministic first pass uses temperature 0. Repeated trials should also be run for providers whose inference remains stochastic.

```bash
python scripts/run_lccb_openai_compatible.py \
  --pack artifacts/lccb-pack \
  --output artifacts/raw-responses.jsonl \
  --stages 0,100,1000 \
  --temperature 0 \
  --repeat 3
```

The runner makes one batched API request per cognitive age per repeat and emits task-level raw response artifacts with prompt/response hashes. It never opens evaluator labels.

## 4. Score independently

Only the evaluator process may open the private labels.

```bash
python scripts/score_lccb_responses.py \
  --pack artifacts/lccb-pack \
  --responses artifacts/raw-responses.jsonl \
  --output artifacts/scored-results.json
```

Primary deterministic metrics are fact recall accuracy, provenance/source recall, stale-error rate, unauthorized-action rate, and completion rate.

## 5. Required comparisons for the paper

At minimum report:

1. deterministic sanity baselines (`always_unknown`, `first_observed`, `latest_structured`);
2. frozen base-model/no-persistent-cognition control;
3. AgentOS at age 0 / 100 / 1000 under an unchanged capability envelope;
4. retrieval-only/no-supersession ablation;
5. no-reconciliation ablation;
6. governance ablation for authority-sensitive tasks.

For cross-model continuity, run a separate experiment series because the model condition intentionally changes.

## 6. Evidence preservation

Preserve together:

- frozen pack `manifest.json`;
- public pack artifacts;
- raw response JSONL;
- scored result JSON;
- exact git commit SHA;
- model condition identifier/version;
- evaluator/rubric version;
- repeat/seed information;
- Cognitive Observatory snapshot/delta references where applicable.

Do not report planned values as empirical results. Deterministic CI validates the harness; only actual provider runs validate longitudinal cognitive performance.
