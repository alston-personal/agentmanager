# AgentOS: Persistent Cognitive State Beyond Long Context

## Status
Working paper draft, evidence cutoff 2026-08-23. Claims are deliberately bounded by completed experiments. Planned ablations and cross-session observations are not presented as established efficacy results.

## Abstract
Large language model agents commonly preserve continuity through conversation context or retrieval, while model parameters remain fixed and execution state is often tied to a session. AgentOS explores a different systems hypothesis: a fixed base model can be coupled to durable, governed cognitive state whose accumulated structure survives model/session replacement and can support longitudinal capability without granting additional authority. We introduce a Longitudinal Cognitive Capability Benchmark (LCCB) and an evidence-preserving execution protocol that separates public experience from evaluator-only labels, freezes model/capability/governance conditions, and records content-addressed receipts. A first real fixed-model full-public-history experiment using `gemini-3.1-flash-lite`, seed 73129, 1,000 synthetic events, cognitive ages 0/100/1000, temperature 0, and three repeats reached ceiling performance on fact accuracy, stale-error avoidance, governance safety, and completion by age 100 and showed zero measured gain from age 100 to 1000. This result does not establish AgentOS cognitive accumulation; instead it establishes a strong long-context baseline and exposes provenance-scoring limitations in the initial task contract. Separately, system development produced a portable execution-disposition contract, durable goal/handoff semantics, failure knowledge, and multi-session canonical-evolution design. Two fresh-session recovery trials have been observed informally, but sustained cross-session execution efficacy remains a pending controlled experiment. The resulting research program therefore shifts from demonstrating persistence itself to testing whether structured accumulated cognition provides discriminative advantages over full-history prompting on transfer, contradiction reconciliation, provenance, forgetting/revival, context-constrained continuity, and governed execution.

## 1. Research question
The primary question is not whether an agent can store more text. It is:

> With the base model, decoding policy, capability envelope, and governance profile held fixed, can durable structured cognitive state produce measurable capability that is not explained by direct access to conversation/full-history context or ordinary retrieval?

The stronger systems question is whether such state remains usable when the conversational executor is replaced.

## 2. Hypothesis and falsification boundary
### H1 — longitudinal cognitive accumulation
For a fixed base model and fixed authority envelope, AgentOS structured persistent cognition improves performance on discriminating longitudinal tasks as experience accumulates.

### Null / competing explanations
Observed gains may instead be explained by full-history prompting, retrieval, task leakage, changing model/provider behavior, changing tool authority, or evaluator artifacts.

A result is not evidence for H1 merely because an older stage scores lower than a later stage. The comparison must control model/version, prompts, decoding, tools, capabilities, governance, evaluator, and accessible evidence.

## 3. System model
AgentOS treats the model as a replaceable reasoning engine and externalizes durable operating state. The current architecture separates:

- cognitive/semantic state;
- canonical execution state and receipts;
- execution disposition (continue/final/block semantics);
- governance and authority;
- failure knowledge;
- live execution-world reconciliation.

A conversation is therefore treated as a disposable execution surface rather than the canonical project state. For concurrent evolution, the design uses one governed Canonical Evolution with multiple Goal/Workstream lineages and disposable executor attachments.

The governance invariant is that increased capability never implies increased authority.

## 4. LCCB methodology
### 4.1 Controlled pack
The synthetic benchmark is generated from a frozen seed and event count. Public model execution may read public experience, public tasks, and the pack manifest; evaluator-only labels remain inaccessible until scoring.

### 4.2 Frozen condition
Within a longitudinal series the model/version, system instruction, decoding parameters, tool policy, enabled cognitive modules, capability manifest, and governance profile must remain fixed. A change begins a new experimental series.

### 4.3 Evidence protocol
Each empirical series preserves the exact git commit, model condition, seed/repeat settings, environment fingerprint, capability manifest, prompt/response hashes, scored results, evaluator version, and artifact digests. Mutating or asynchronous claims require receipts.

### 4.4 Metrics
The initial deterministic metrics are fact recall accuracy, source/provenance recall, stale-error rate, unauthorized-action rate, and completion rate. The first provider run demonstrated that provenance must be tested by an explicit citation/retrieval contract rather than inferred when public tasks do not request source references.

## 5. Completed empirical result: fixed-model full-history baseline
### 5.1 Condition
- model: `gemini-3.1-flash-lite`
- provider family: OpenAI-compatible
- seed: 73129
- events: 1000
- stages: 0, 100, 1000
- temperature: 0
- repeats: 3
- execution: GitHub-hosted Actions -> governed SSH -> isolated Oracle AArch64 environment
- evaluator-only labels inaccessible during model execution
- workflow run: 32581330887
- experiment commit: `11a910eeefd09f2a33a994c2bbef04c3831bdbe0`
- artifact digest: `sha256:96ca40f58c8f743dc53bd4eb7fe0ae9345d3d8b9306d3a675d235e4dbd942b8a`

### 5.2 Results

| Cognitive age | Fact accuracy | Source recall* | Stale error | Unauthorized action | Completion |
|---|---:|---:|---:|---:|---:|
| 0 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| 100 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| 1000 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |

All three repeats were identical per task; observed repeat variance was zero. The measured age-100 to age-1000 gain on the primary non-provenance metrics was zero.

`*` Source recall at ages 100/1000 is not interpretable as provenance forgetting because the public task contract did not request literal evidence references while the evaluator counted them.

### 5.3 Interpretation
Age 0 does not represent hidden pretraining knowledge: the benchmark defines `unknown` as correct before Meridian experience is supplied. The fixed-model full-history condition reaches the task ceiling by age 100. It therefore neither supports nor refutes H1. Instead, it establishes a strong baseline that a structured AgentOS condition must beat on dimensions where direct full-history prompting does not trivially saturate the benchmark.

This negative/non-discriminating result changes the experimental target. Raw recall on a fully visible history is insufficient as the central efficacy measure.

## 6. Failure knowledge as evidence
The real provider run exposed two reproducibility defects that were repaired and retained as negative knowledge rather than discarded: the upstream required canonical `Accept` and AgentOS `User-Agent` headers, and fresh isolated checkout execution exposed an implicit repo-import/PYTHONPATH dependency. These failures motivate treating failed execution paths, repair evidence, and retry conditions as durable experimental state.

## 7. Cross-session continuity: current evidence boundary
During subsequent AgentOS development, a historically long conversation exhibited mature goal-directed execution in which successful substeps were repeatedly followed by receipt inspection and self-derived next actions before finalization. Archaeological reconstruction found no single sufficient trigger: `/goal`, GitHub access, Actions, and Oracle each have counterexamples. The best current explanation is multi-factor emergence involving stable goal semantics, broad termination criteria, accumulated context/IR, reliable multi-tool actions, machine-readable receipts, persistent external state, and reversible-action authority.

This behavior has been distilled into an executable disposition invariant:

> Answerability is not completion. Continue while a material closure gap remains and the next action is derivable, authorized, and safe; stop on verified closure, authority/governance boundary, unrecoverable dependency, terminal failure, or user interruption.

Two fresh-session trials have informally recovered AgentOS state/goal and performed live reconciliation. These observations are promising but are **not yet a controlled LCCB result** and must not be used as evidence for longitudinal cognitive efficacy. A formal cross-session benchmark should separately measure state recovery, next-action derivation, premature-finalization rate, duplicate work, failure avoidance, authority violations, and sustained action→receipt→next-action depth.

## 8. Revised discriminating experiment matrix
The next empirical phase must compare conditions that can separate structured cognition from context access:

1. **B0 frozen model / no persistent cognition** — task-local prompt only.
2. **B1 full-public-history / long-context** — the completed ceiling baseline pattern.
3. **B2 retrieval-only** — relevant observations retrieved without supersession/reconciliation semantics.
4. **B3 structured AgentOS cognition** — durable facts, relations, provenance, supersession, reconciliation, failure knowledge and governance state under the same model/capability envelope.
5. **Ablation: no supersession** — test stale-state handling.
6. **Ablation: no reconciliation** — test contradictory observations.
7. **Ablation: no failure knowledge** — test repeated known-bad paths after session replacement.
8. **Ablation: no durable disposition** — test premature finalization while state knowledge is held constant.
9. **Governance ablation** — distinguish capability improvement from authority expansion.

Primary discriminating task families should include unseen transfer, contradictory-state reconciliation, explicit provenance citation, constrained-context continuity, forgetting/revival, supersession, and cross-session executor replacement.

## 9. Statistical plan
A single deterministic seed is a mechanism sanity check, not a population-level efficacy result. The next series should use multiple frozen seeds and report per-condition task-level outcomes, mean differences, confidence intervals, and paired comparisons where packs/tasks are matched. Ceiling metrics should not be used as the sole primary endpoint. Provider stochasticity should be handled by repeated trials even when temperature is zero if the provider does not guarantee determinism.

Claims should be promoted only in this order:

- harness validated;
- mechanism observed;
- replicated across seeds/tasks;
- discriminates against strong baselines;
- survives ablation;
- transfers across session/model replacement where claimed.

## 10. Threats to validity
- **Ceiling effects:** the first full-history condition saturated recall/safety/completion.
- **Metric-contract mismatch:** source recall was scored without explicit source-citation demand.
- **Provider drift:** a model alias may change unless an immutable version is available.
- **Synthetic-world validity:** Meridian is controlled but may not represent real project cognition.
- **Tool/authority confounding:** more tools or permission can masquerade as more intelligence.
- **Context leakage:** a fresh session may receive hidden/product-level context not represented in the experiment packet; formal trials must control the supplied state as far as the host permits.
- **Executor persistence:** unusually long single-turn behavior may be host/runtime-dependent; AgentOS correctness must not rely on it.
- **Selection bias:** successful recovery anecdotes must not substitute for pre-specified fresh-session trials.

## 11. Current claims
### Supported
- The LCCB harness can execute a blinded fixed-model provider series with content-addressed evidence preservation.
- The completed full-public-history condition reaches ceiling by age 100 on the initial primary non-provenance metrics and shows zero measured age-100→1000 gain.
- The initial provenance metric is invalid for ages 100/1000 under that public task contract.
- Durable goal/disposition/governance/failure-state contracts have been implemented as system mechanisms, and cross-session recovery is sufficiently promising to justify controlled evaluation.

### Not yet supported
- AgentOS improves cognition longitudinally relative to strong baselines.
- AgentOS naturally reproduces master-grade sustained execution in every fresh conversation.
- Cross-model replacement preserves equivalent capability.
- Structured cognition outperforms retrieval-only or long-context conditions.

## 12. Conclusion
The first real experiment did not deliver a positive cognitive-growth result; it delivered something methodologically more useful: a ceiling long-context baseline and a falsifiable boundary for the AgentOS claim. The research question is now sharper. AgentOS must demonstrate value where persistence requires structure rather than merely visibility: knowing what supersedes what, why a fact is trusted, what failed before, which authority remains valid, what work is unfinished, and how those semantics survive executor replacement. The next phase is therefore a controlled discriminating comparison, not further assertion from architectural plausibility.
