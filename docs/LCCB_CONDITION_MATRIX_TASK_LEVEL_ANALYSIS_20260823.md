# LCCB Experiment 2 — Task-Level and Repeat-Level Analysis

**Source experiment:** completed B0-B3 fixed-model condition matrix  
**Workflow run:** `32615130545`  
**Experiment SHA:** `561e878ba502e54ef81b947b57a88a47f8bad79a`  
**Artifact ID:** `9486716442`  
**Artifact digest:** `sha256:196df7ae2147fb9fdd7e03669e1d8725929ed93e2d734e1acae372f45e55b992`

## 1. Purpose

The manuscript reports aggregate B0-B3 metrics. This addendum re-examines the preserved raw responses at the task and provider-repeat level to determine whether the B2 degradation is diffuse noise or a specific failure mode, and whether the small B1/B3 provenance difference has a concrete source.

No new model calls are used here. This is a deterministic post-hoc decomposition of the immutable completed Experiment 2 artifact. The primary benchmark result is unchanged.

## 2. Frozen task set

Each stage contains 13 tasks:

- 6 service-owner state tasks;
- 3 procedure tasks;
- 3 governance/capability tasks;
- 1 continuity/next-work task.

At age 100 and age 1000, B1 and B3 achieved fact accuracy `1.0` on every repeat. Their fact answers therefore provide a direct audit trail for which expected benchmark atom was present in each response. The canonical score remains the hidden-label evaluator; this decomposition does not replace it.

## 3. B2 at age 100: 7/13 facts correct

The B2 retrieval-only condition achieved `0.5384615 = 7/13` fact accuracy on all three provider repeats.

### Correct tasks

| Task | B2 answer |
|---|---|
| `governance:meridian.deploy` | `proposal` |
| `state:service-01.owner` | `atlas` |
| `state:service-02.owner` | `boreal` |
| `state:service-03.owner` | `cirrus` |
| `state:service-04.owner` | `delta` |
| `state:service-05.owner` | `atlas` |
| `state:service-06.owner` | `boreal` |

### Not recovered

B2 answered `unknown` for:

- `continuity:next-work`;
- `governance:meridian.billing.adjust`;
- `governance:meridian.rollback`;
- `procedure:deploy-1`;
- `procedure:deploy-2`;
- `procedure:deploy-3`.

The stale-error rate was still `0.0`: at this stage the retrieved facts it did answer were not yet obsolete.

## 4. B2 at age 1000: 4/13 facts correct and 3/13 stale

At age 1000, B2 fact accuracy fell to `0.3076923 = 4/13`, while stale-error rate rose to `0.2307692 = 3/13`. These metrics were identical across all three provider repeats.

### Facts that remained correct

Only four service-owner tasks remained correct:

| Task | Current B2 answer | Revision status in benchmark |
|---|---|---|
| `state:service-03.owner` | `cirrus` | unchanged from initial public fact |
| `state:service-04.owner` | `delta` | unchanged from initial public fact |
| `state:service-05.owner` | `atlas` | unchanged from initial public fact |
| `state:service-06.owner` | `boreal` | unchanged from initial public fact |

### Previously correct facts that became stale

Exactly three age-100 B2 successes later received authoritative revisions, and exactly those three became stale B2 answers at age 1000:

| Task | Age-100 B2 | Age-1000 current truth (B1/B3, evaluator-confirmed) | Age-1000 B2 |
|---|---|---|---|
| `state:service-01.owner` | `atlas` | `boreal` | `atlas` |
| `state:service-02.owner` | `boreal` | `cirrus` | `boreal` |
| `governance:meridian.deploy` | `proposal` | `allow` | `proposal` / `proposal-only` |

The remaining six tasks stayed unrecovered rather than becoming stale.

## 5. Interpretation of the B2 degradation

This decomposition materially sharpens the aggregate result.

The age-100 to age-1000 B2 decline is not a random three-task fluctuation. The entire loss from `7/13` to `4/13` is accounted for by three tasks whose earlier values were later superseded. The four B2 facts that stayed correct are precisely the owner keys that remained unchanged. The stale-error count at age 1000 is also exactly three tasks.

For this tested lexical retrieval policy, the observed failure mode is therefore consistent with **revision blindness / supersession failure**, not merely insufficient prompt length. B2 is the smallest condition, yet it preserves obsolete evidence for revised keys. B3 is larger than B2 but explicitly retains current-state semantics and remains fact-perfect.

This supports the manuscript's bounded causal interpretation:

> Compactness alone does not explain B3. In the tested series, explicit current-state/supersession structure preserves revised truth that lexical relevance without supersession semantics does not.

It still does **not** establish that all retrieval-augmented systems fail. A retrieval system with temporal constraints, revision graphs, authoritative-source ranking, or explicit state reconciliation could be a stronger baseline and should be tested separately.

## 6. Repeat stability

### Fact and stale metrics

- B2 age 100: `7/13` fact accuracy on all 3 repeats; stale `0/13` on all repeats.
- B2 age 1000: `4/13` fact accuracy on all 3 repeats; stale `3/13` on all repeats.
- B3 age 100 and age 1000: `13/13` fact accuracy and `0/13` stale tasks on all 3 repeats.
- B1 age 100 and age 1000: `13/13` fact accuracy and `0/13` stale tasks on all 3 repeats.

Thus the primary fact/stale contrast between B2 and B3 is repeat-stable within this provider series.

### Response-format variation

Temperature `0` did not make textual outputs fully deterministic. B3 sometimes emitted `source_ref: <ref>` and sometimes only `(<ref>)`; these formatting differences did not change fact or source scoring because the literal source reference remained present.

B2 also varied once between `proposal` and `proposal-only` for the same stale governance evidence without changing the score.

## 7. Why B1 provenance varied while B3 did not

At age 1000:

- B3 source recall was `0.8125 = 13/16` on all three repeats.
- B1 source recall was `0.8125`, `0.7500`, and `0.8125`, averaging `0.7916667`.

The one lower B1 repeat is traceable to a single task: `procedure:deploy-3`.

Two public procedure-revision events, `lccb:meridian:event:0520` and `lccb:meridian:event:0880`, carry the same current procedure text (`validate -> stage -> policy-check -> canary -> promote`). One B1 repeat cited event `0520`, while the hidden evaluator's canonical current source was the later event `0880`. The fact answer remained fully correct, but one provenance hit was lost.

B3 exposes only the latest event for that semantic key and therefore cited `0880` consistently.

This is evidence of a **provenance recency/stability advantage in this specific case**, but the manuscript should not promote it into a broad provenance claim because the benchmark still has an unresolved proof-set semantic for the continuity task. In particular, the continuity label expects all contributing work-state sources while a concise answer naturally cites only the decisive ready-work event.

## 8. Statistical boundary

This experiment uses one synthetic world seed and three provider repeats. The repeated calls are not independent benchmark worlds, and the 13 tasks are heterogeneous rather than an i.i.d. population sample. Therefore a narrow binomial confidence interval over the 39 repeated task calls would overstate inferential certainty.

The strongest valid statement from this artifact is exact and within-pack:

- B1 and B3 were fact-perfect on every tested task and repeat at ages 100 and 1000;
- B2 was `7/13` at age 100 and `4/13` at age 1000 on every repeat;
- the three-task B2 loss corresponds exactly to three superseded items that became stale;
- B1/B3 prompt cost diverged sharply, with B3 using 93.49% fewer characters at age 1000.

Population-level claims require pre-specified multiple seeds/worlds, ideally with matched task instances and bootstrap or hierarchical uncertainty across worlds rather than treating repeated provider calls as independent samples.

## 9. Manuscript implication

The aggregate Experiment 2 conclusion remains unchanged, but its mechanism is now more directly supported:

> **Within the tested Meridian world, B2's longitudinal degradation is localized to revision and supersession handling. Structured current state prevents those stale regressions while preserving every measured fact, and it does so with far less context than full-history B1.**

The next discriminating experiment should therefore stress the number and density of authoritative revisions rather than merely add irrelevant history. That is the rationale for `lccb-revision-stress-v1`; its current external-provider execution status is documented separately as `PROTOCOL_READY_PROVIDER_BLOCKED`.
