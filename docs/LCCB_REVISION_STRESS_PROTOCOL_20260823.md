# LCCB Experiment 3 — Dense Revision Stress Protocol

**Status:** `PROTOCOL_READY_PROVIDER_BLOCKED`  
**Date:** 2026-08-23  
**Target comparison:** B1 full public history vs B3 structured current public state

## 1. Why this experiment exists

The completed B0-B3 condition matrix established a strong context-compression result but did not establish capability beyond full history. At age 1000, B1 and B3 both achieved perfect fact accuracy and zero stale-error rate. The existing Meridian stream contains comparatively few semantic revisions among many background events, so the model can still recover current facts from the complete history.

Experiment 3 is designed to remove that ceiling-friendly property without changing the model, tools, authority, or evidence boundary. It turns longitudinal history into a dense supersession problem: almost every event changes an authoritative semantic value. The scientific question is whether explicit current-state structure becomes behaviorally useful when raw-history replay must resolve thousands of obsolete values.

## 2. Frozen design

| Variable | Frozen value |
|---|---|
| Experiment ID | `lccb-revision-stress-v1` |
| Model | `gemini-3.1-flash-lite` |
| Seed / series identity | `73129` |
| Public events | `4,000` |
| Semantic revision events | `4,000` |
| State keys | `24` |
| Stages | `0, 1000, 4000` |
| Conditions | `B1, B3` |
| Temperature | `0` |
| Provider repeats | `3` |
| Private evaluator labels | physically separated; permission-blocked during model execution |
| Execution route | GitHub-hosted Actions -> governed SSH -> isolated Oracle workspace |

### B1 — Full-history replay

B1 receives the complete ordered public event stream visible at the tested stage. No event is truncated or summarized by the benchmark. The fixed model must infer the latest authoritative value for every queried key while ignoring all superseded values.

### B3 — Structured current state

B3 is derived from the identical public event stream by the existing structured-state projector. For each semantic key it exposes only the latest public authoritative event. It receives no private label, hidden answer, new tool, or broader authority.

The intended causal contrast is therefore **history replay versus explicit current-state representation**, not more information versus less information and not more permission versus less permission.

## 3. Synthetic stress world

The builder `scripts/build_lccb_revision_stress_pack.py` creates 24 service-owner keys and cycles through them for 4,000 authoritative updates. Each update emits a new unique value such as `owner-07-r0124` and explicitly marks the previous value as superseded. Hidden labels track the current value and retain prior values as forbidden stale answers.

At stage 4000, each key has accumulated approximately 166–167 authoritative versions. A correct B1 answer therefore requires resolving a long chain of supersession for every queried key; B3 exposes only the terminal public state for those same chains.

The private labels are not needed to construct either condition and remain inaccessible during model execution.

## 4. Pre-specified interpretation

A successful run may support one of three outcomes:

1. **B1 = B3:** structured state remains primarily a context-efficiency result under this stress level.
2. **B3 > B1:** explicit current-state semantics provide measured capability/robustness beyond raw full-history replay for this task family.
3. **B1 > B3:** the projector has discarded decision-relevant information; the AgentOS representation hypothesis requires revision.

Prompt-size differences are descriptive. A cognitive superiority claim requires scored task differences, not merely fewer characters.

Provider rejection, timeout, quota exhaustion, HTTP 429, workflow failure, or artifact failure is **not** scored as a cognitive error unless the experimental task explicitly measures those operational properties.

## 5. Execution attempt 1

| Field | Receipt |
|---|---|
| Workflow run | `32617741853` |
| Experiment SHA | `6208daeb7a194f1c595f55ea3f65976b64d6aa61` |
| Result | workflow failure |
| Artifact | none |
| Failure class | provider `HTTP 429` |

Checkout, SSH transport, Oracle workspace creation, and stress-pack construction completed. The external provider then returned HTTP 429 before a complete response set could be scored. Because the runner did not yet emit condition/stage trace lines, this attempt establishes only a serving failure, not which public prompt size triggered it.

No B1/B3 scientific result is derived from this run.

## 6. Bounded serving repair

The matrix runner was modified to make serving failures observable without changing experimental semantics:

- trace every provider call with repeat, condition, stage, and prompt characters;
- retry **only** `HTTP 429`;
- bound retries to three;
- use exponential delays of 30, 60, and 120 seconds;
- pace successful calls by eight seconds;
- leave model, temperature, prompt construction, public evidence, hidden evaluator, tasks, and conditions unchanged.

This repair is operational rather than cognitive. It prevents a transient provider throttle from being silently confused with a model answer.

## 7. Execution attempt 2

| Field | Receipt |
|---|---|
| Workflow run | `32617901460` |
| Experiment SHA | `c895aa4c307f788d5d9a6ddc260595e0031c65d3` |
| First call | repeat 0, B1, stage 0 |
| First-call prompt | `6,390` characters |
| Retry delays | `30, 60, 120` seconds |
| Result | workflow failure |
| Artifact | none |
| Failure class | persistent provider `HTTP 429` |

The trace is decisive for diagnosis. The first attempted model call was **B1 at stage 0**, before any 4,000-event full-history payload is present. Its prompt was only 6,390 characters. The provider returned HTTP 429 immediately and again after each bounded backoff interval.

Therefore the two failed attempts do **not** show that full-history B1 exceeded a context limit. The provider was unavailable or quota/rate limited even for the small stage-0 request. Treating these failures as evidence for B3 would be scientifically invalid.

## 8. Current evidence boundary

Experiment 3 is implemented, frozen, externally attempted, and diagnosable, but **not completed**. The correct manuscript status is:

> `PROTOCOL_READY_PROVIDER_BLOCKED`

The following claims are prohibited from these runs:

- B3 beats B1 under dense revision stress;
- B1 fails because 4,000 events exceed model context;
- structured state avoids provider rate limits;
- failed workflow execution counts as a task error.

The failed receipts are still useful research evidence because they establish a concrete operational dependency: a benchmark that relies on an external provider must distinguish serving availability from cognitive performance.

## 9. Valid completion criterion

The frozen series may be considered completed only when a run:

1. successfully obtains provider responses for all pre-specified B1/B3 stage/repeat combinations;
2. keeps evaluator-only labels inaccessible until model execution finishes;
3. emits raw responses and deterministic scores;
4. uploads the manifest and evidence artifact;
5. records workflow run, exact experiment SHA, artifact ID, and artifact digest;
6. reports failures separately rather than deleting the prior 429 receipts.

Until then, Experiment 2 remains the latest completed cognitive comparison, and its bounded conclusion remains unchanged: structured state matches full-history fact performance with dramatically less context and outperforms the tested retrieval-only baseline, but capability beyond full history is still unestablished.

## 10. Reproducibility assets

- Builder: `scripts/build_lccb_revision_stress_pack.py`
- Workflow: `.github/workflows/lccb-revision-stress-oracle.yml`
- Matrix runner: `scripts/run_lccb_condition_matrix.py`
- Attempt record: `research/results/lccb-revision-stress-attempts-20260823.json`
- Builder commit: `8732a79196d8086029b8a03bca0d48e0fdccd54b`
- Workflow commit: `e745e1b9fbfb8177c4717de0ebbeabfcb0a446bb`
- Bounded-retry runner commit: `d2f248da9025adf5b2b39ad309654a1e6145a395`
- Failed run 1: `32617741853`
- Failed run 2: `32617901460`

This document is an experimental protocol and failure-analysis addendum. It must not be cited as a positive B1/B3 efficacy result until the valid completion criterion is satisfied.
