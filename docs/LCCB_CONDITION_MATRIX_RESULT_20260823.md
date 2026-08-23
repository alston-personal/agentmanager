# LCCB B0-B3 Condition Matrix — Completed Result (2026-08-23)

## Status

Completed external fixed-model experiment. This result is empirical evidence, not a planned experiment.

Immutable execution receipt:

- Workflow: `LCCB Condition Matrix Oracle Experiment`
- Run: `32615130545`
- Experiment SHA: `561e878ba502e54ef81b947b57a88a47f8bad79a`
- Artifact: `9486716442`
- Artifact digest: `sha256:196df7ae2147fb9fdd7e03669e1d8725929ed93e2d734e1acae372f45e55b992`
- Model: `gemini-3.1-flash-lite`
- Seed: `73129`
- Events: `1000`
- Ages: `0, 100, 1000`
- Temperature: `0`
- Repeats: `3`
- Route: GitHub-hosted Actions -> governed SSH -> isolated Oracle workspace -> OpenAI-compatible provider.

Evaluator-only labels were permission-blocked during provider execution and restored only for deterministic scoring.

## Conditions

| Condition | Supplied state |
|---|---|
| B0 | task-local prompt with no prior Meridian experience |
| B1 | all visible public history through the cognitive age |
| B2 | compact lexical retrieval-only evidence; no explicit supersession semantics |
| B3 | compact structured current-state projection retaining the latest public semantic value per key |

B3 in this experiment is deliberately narrower than “all of AgentOS.” It tests the value of explicit current-state/supersession structure, not failure memory, workstream integration, durable disposition, or executor replacement.

The revised system instruction explicitly requires supporting `source_ref` values for known answers, repairing the largest task/metric mismatch found in the first fixed-model run.

## Aggregate results

### Age 0

All conditions correctly return benchmark-defined `unknown`, so fact and source accuracy are 1.0. Age 0 remains a negative control rather than evidence of pretrained Meridian knowledge.

### Age 100

| Condition | Fact accuracy | Source recall | Stale error | Unauthorized | Completion | Prompt chars |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 3,040 |
| B1 | 1.0000 | 0.8125 | 0.0000 | 0.0000 | 1.0000 | 59,515 |
| B2 | 0.5385 | 0.4375 | 0.0000 | 0.0000 | 1.0000 | 11,938 |
| B3 | 1.0000 | 0.8125 | 0.0000 | 0.0000 | 1.0000 | 36,129 |

At age 100, B3 matches B1 on fact accuracy and stale-error rate while using 39.3% fewer prompt characters.

### Age 1000

| Condition | Fact accuracy | Source recall | Stale error | Unauthorized | Completion | Prompt chars |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 3,041 |
| B1 | 1.0000 | 0.7917 | 0.0000 | 0.0000 | 1.0000 | 563,209 |
| B2 | 0.3077 | 0.2500 | 0.2308 | 0.0000 | 1.0000 | 11,939 |
| B3 | 1.0000 | 0.8125 | 0.0000 | 0.0000 | 1.0000 | 36,637 |

At age 1000:

- B3 fact accuracy minus B1 = `0.0000`.
- B3 therefore does **not** establish capability superiority over full history on these tasks.
- B3 uses 36,637 prompt characters versus B1's 563,209: 6.51% as many characters, a 93.49% reduction.
- B3 fact accuracy minus B2 = `+0.6923`.
- B3 stale-error minus B2 = `-0.2308`.
- B2 becomes both incomplete in fact recovery and stale under age growth despite being the smallest non-null memory condition.

## Interpretation

The matrix changes the evidence boundary in three useful ways.

First, **structured current-state projection is empirically sufficient to preserve full-history fact performance in this synthetic world while radically reducing input size at age 1000.** This is evidence for context efficiency and explicit supersession semantics, not evidence that B3 is intrinsically more capable than a model given all history.

Second, **retrieval-only memory is not an adequate substitute under this retrieval policy.** B2 degrades from 0.5385 fact accuracy at age 100 to 0.3077 at age 1000 and acquires a stale-error rate of 0.2308. The result is consistent with the hypothesis that current-state semantics matter when history contains revisions and distractors. Because only one retrieval algorithm was tested, it does not establish that all retrieval architectures fail.

Third, **the strongest central AgentOS efficacy claim remains open.** B3 ties B1 on fact accuracy rather than exceeding it. A claim that structured cognition creates capability unavailable to full history still requires harder pre-specified tasks: context-budget overflow, cross-event relational transfer, failure-memory reuse, work continuation after executor replacement, trust/provenance conflicts, and governance divergence.

## Provenance limitation after task-contract repair

The second experiment explicitly asked the model to emit `source_ref` values, so the original “citations were never requested” defect is repaired. Source recall nevertheless remains below 1.0 for B1/B3 at later ages. Manual inspection shows that individual answers usually contain the directly selected source receipt. The remaining gap is concentrated in evaluator semantics where a continuity answer may be supported by multiple work-state receipts, while the response naturally cites the chosen ready-work receipt only.

Therefore source recall is now more interpretable than in the first run but still should not be promoted to a clean primary endpoint until the evidence-set contract specifies whether the expected answer requires one decisive source, all supporting sources, or a minimal sufficient proof set.

## Reproducibility and failure receipts

Two failed attempts immediately preceding the successful matrix are retained as failure knowledge:

1. Run `32614903376` failed because the new workflow attempted `git archive` before checking out the repository. The failure was localized from `fatal: not a git repository` and repaired by adding `actions/checkout`.
2. Run `32614940543` then failed because the experiment initially assumed remote variables named `AGENTOS_AI_API_KEY` / `AGENTOS_AI_BASE_URL`. Provider-readiness evidence showed the verified Oracle contract is `AI_API_ACADEMIA_KEY` / `AI_API_BASE_URL`; the workflow was aligned with that existing contract rather than inventing a second credential path.

The successful run followed those repairs without relaxing governance or exposing secrets.

## Claim update

Supported now:

- full history reaches ceiling fact accuracy on the current Meridian recall tasks;
- a structured current-state projection matches that fact accuracy at ages 100 and 1000;
- at age 1000 the structured projection does so with a 93.49% smaller prompt by character count;
- the tested retrieval-only baseline is materially worse and becomes stale at age 1000;
- no condition produced unauthorized-action errors in this matrix.

Not supported yet:

- B3 has higher cognitive capability than B1 full history;
- the observed advantage generalizes beyond seed 73129 or Project Meridian;
- all retrieval systems are inferior to structured cognition;
- full AgentOS failure knowledge/disposition/workstream state improves the model under executor replacement;
- persistent cognition constitutes model-weight learning.

The scientifically strongest result at this stage is therefore **structured-state equivalence with large context compression plus superiority over this retrieval-only baseline**, while the stronger “capability beyond full history” hypothesis remains falsifiable and open.
