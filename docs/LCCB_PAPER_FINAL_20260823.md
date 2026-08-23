# AgentOS: Persistent Cognitive State Beyond Long Context

## An Evidence-Bounded Systems Study of Longitudinal Cognition, Governance, and Executor Replacement

**Manuscript status:** evidence-bounded complete manuscript, 2026-08-23. The paper reports completed evidence as results and explicitly separates future experiments from established findings.

## Abstract

LLM agents commonly obtain continuity from a conversation window or retrieval system while model parameters remain fixed and operational state remains coupled to an execution session. AgentOS investigates a stronger systems hypothesis: durable, governed cognitive and execution state can be externalized from the model so that accumulated project semantics survive executor replacement without silently expanding authority. We define the Longitudinal Cognitive Capability Benchmark (LCCB), a controlled evaluation protocol that freezes the model, decoding policy, capability envelope, governance condition, public experience, evaluator, and evidence boundaries. The protocol physically separates public experience from evaluator-only labels and preserves content-addressed execution receipts. A first real fixed-model experiment using `gemini-3.1-flash-lite`, seed 73129, 1,000 synthetic events, cognitive ages 0/100/1000, temperature 0, and three repeats produced ceiling fact accuracy, zero stale-error rate, zero unauthorized-action rate, and full completion at all measured ages; age 100 to 1000 showed zero measured gain. Source-recall values at later ages are not interpretable because the public task contract did not require literal source citations. Consequently, this experiment does not demonstrate longitudinal cognitive improvement. It instead establishes a strong full-history baseline, reveals a provenance-contract defect, and falsifies raw recall under fully visible history as a sufficient primary endpoint. We further report implemented mechanisms for durable goal state, execution disposition, governance separation, failure knowledge, canonical multi-workstream evolution, and live reconciliation, while treating observed fresh-session recovery as preliminary rather than controlled efficacy evidence. The resulting contribution is therefore both architectural and methodological: AgentOS supplies a falsifiable substrate for persistent cognition, and LCCB defines the evidence boundary required to distinguish structured cognitive accumulation from long context, retrieval, changing authority, and evaluator artifacts.

## 1. Introduction

A language model can appear to learn during a long conversation even when its parameters never change. More history becomes available, retrieval can expose prior observations, tools can change, and the surrounding runtime can accumulate state. These effects create a central identification problem: when an agent becomes more capable over time, what actually improved?

AgentOS is motivated by the hypothesis that useful cognitive continuity should not depend on one indefinitely preserved conversation. The model is treated as a replaceable reasoning engine. Durable project semantics, work state, provenance, governance, failure knowledge, and execution receipts are externalized into governed state. A fresh executor should be able to reconstruct the current problem, determine what remains unfinished, respect existing authority, avoid known failed paths, act, observe receipts, and continue until the goal is closed or a real boundary is reached.

This proposition is stronger than memory retrieval. It predicts that structured state should eventually provide advantages that cannot be explained by simply showing the model more history. It also creates additional safety obligations: more accumulated capability must not become more authority.

The present paper asks two related questions:

**RQ1 — Cognitive discrimination.** With the base model, decoding policy, capability envelope, and governance profile held fixed, can durable structured cognitive state produce measurable capability not explained by full-history context or ordinary retrieval?

**RQ2 — Executor replacement.** Can the same governed state support correct continuation after the conversational executor is replaced, without duplicate work, forgotten failures, or authority drift?

The first completed provider experiment does not answer RQ1 positively. Instead, it exposes a ceiling baseline and thereby sharpens the experiment required to answer it. We report that negative/non-discriminating result rather than converting architectural plausibility into an efficacy claim.

## 2. Contributions

This work makes five bounded contributions.

1. **A model-external persistence architecture.** AgentOS separates replaceable reasoning from durable cognitive, execution, governance, failure, and evidence state.
2. **A governance invariant.** Capability discovery and cognitive growth do not grant authority; `Discovered != Registered != Authorized != Active`, and governance may tighten automatically but may not silently relax.
3. **A goal-level execution semantics.** Execution is organized around verified goal closure rather than answerability or arbitrary substep completion.
4. **LCCB.** A controlled benchmark/evidence protocol separates public experience from hidden evaluation labels and freezes competing variables.
5. **A completed fixed-model baseline with a negative result.** Full-public-history prompting saturates the initial benchmark, demonstrating that raw recall is not sufficiently discriminating and that provenance requires an explicit task contract.

## 3. AgentOS system model

### 3.1 Replaceable executor, durable state

AgentOS treats a conversation/session as an execution surface rather than the canonical source of truth. Durable state is divided conceptually into:

- semantic/cognitive state: current facts, relations, procedures, provenance and supersession;
- goal/work state: objectives, closure invariants, dependencies and next gaps;
- execution state: observations, decisions, actions and receipts;
- execution disposition: continue/final/block semantics;
- governance state: capability discovery, registration, authorization and activation;
- failure knowledge: failed paths, diagnoses, repairs and retry conditions;
- reconciliation state: differences between persisted belief and the current execution world.

This decomposition is intended to make executor replacement possible without treating a transcript as the operating system.

### 3.2 Goal-level execution

The central execution invariant is:

> **Answerability is not completion.**

After every material receipt, the executor reassesses the goal. If a closure gap remains and the next action is derivable, authorized, and safe, execution continues. A final response is appropriate only when closure is verified, new authority is required, necessary information is unavailable, a governance/risk boundary is reached, an unrecoverable dependency blocks progress, or the user interrupts/supersedes the goal.

This distinguishes goal-directed execution from a common conversational loop in which one meaningful substep is completed and control is returned to the user even though the requested goal remains open.

### 3.3 Canonical evolution and concurrent work

Executor replacement does not imply that only one session may exist. AgentOS instead separates one governed canonical evolution from multiple concurrent workstreams. Each workstream carries goal lineage, its observed canonical parent, closure invariants, dependencies, ownership/lease information, receipts, failures, and integration disposition. Effectful ownership includes fencing identity so two executors cannot silently become simultaneous writers to the same workstream. Workstream completion and canonical integration are separate states.

The design principle is: many executors may contribute, but no executor independently defines canonical history.

### 3.4 Governance

The governing safety law is:

> **Capability must never scale faster than governance.**

The architecture therefore separates discovery, registration, authorization, and activation. New cognition does not imply new permission. External effects require scoped authority; discovery cannot self-grant permission; governance may tighten automatically but may not self-relax; credentials remain local where possible; and execution success is never inferred without a receipt.

## 4. Longitudinal Cognitive Capability Benchmark

### 4.1 Identification problem

A longitudinal agent experiment is invalid if an apparent gain can be explained by a different model, prompt, decoder, tool set, permission profile, hidden information, evaluator, or task distribution. LCCB therefore treats these as experimental conditions rather than implementation details.

### 4.2 Controlled synthetic world

The current controlled world, Project Meridian, is generated deterministically from a frozen seed. It emits public `ExperienceEvent` records containing state observations, procedures, governance modes, work-state transitions, revisions/supersessions, and irrelevant background telemetry. Evaluator labels are generated from the hidden world state and stored separately.

The same task keys are evaluated at ages 0, 100, and 1000. At age 0, before benchmark experience is supplied, `unknown` is explicitly correct. Later labels track current state and mark superseded values as forbidden. This pairing makes longitudinal comparisons deterministic, but—as the completed experiment demonstrates—also creates a ceiling risk when full history is directly visible.

### 4.3 Evidence isolation

Public execution may consume public experience, public task prompts, and the public manifest. Hidden labels are evaluator-only. The deterministic evaluator runs outside AgentOS authority and does not mutate cognition, project state, or governance.

### 4.4 Frozen experimental condition

Within a longitudinal series, the following must remain fixed:

- model/version reference;
- system instruction and task contract;
- decoding parameters;
- tool policy and capability manifest;
- enabled cognitive modules;
- governance profile;
- benchmark pack and seed;
- evaluator/rubric.

A change in these variables starts a new series rather than being interpreted as longitudinal improvement.

### 4.5 Metrics

The initial evaluator reports:

- fact recall accuracy;
- source/provenance recall accuracy;
- stale-error rate;
- unauthorized-action rate;
- completion rate.

Expected and forbidden facts are literal benchmark atoms, making the canonical score deterministic and auditable. A semantic judge may be added as a secondary condition but must not silently replace the deterministic evaluator.

## 5. Completed fixed-model experiment

### 5.1 Experimental condition

The first real provider series used:

| Variable | Value |
|---|---|
| Model | `gemini-3.1-flash-lite` |
| Provider interface | OpenAI-compatible |
| Seed | 73129 |
| Synthetic events | 1,000 |
| Cognitive ages | 0, 100, 1000 |
| Temperature | 0 |
| Repeats | 3 |
| Execution route | GitHub-hosted Actions -> governed SSH -> isolated Oracle AArch64 workspace |
| Workflow run | `32581330887` |
| Experiment commit | `11a910eeefd09f2a33a994c2bbef04c3831bdbe0` |
| Artifact digest | `sha256:96ca40f58c8f743dc53bd4eb7fe0ae9345d3d8b9306d3a675d235e4dbd942b8a` |

Evaluator-only labels were inaccessible during model execution and restored only for scoring.

### 5.2 Results

| Cognitive age | Fact accuracy | Source recall* | Stale error | Unauthorized action | Completion |
|---|---:|---:|---:|---:|---:|
| 0 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 |
| 100 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |
| 1000 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 |

All three repeats were identical per task under the observed provider condition. The measured gain from age 100 to age 1000 on the primary non-provenance metrics was **0**.

`*` The later-age source-recall score is not an interpretable provenance result. Public prompts asked for the answer but did not require literal source references, while the evaluator counted those references. The measurement contract and task contract therefore disagreed.

### 5.3 Interpretation

The age-0 score is not evidence that the model knew hidden Meridian state: `unknown` is the benchmark-defined correct response before experience is supplied. Once history is available, the full-history condition reaches the ceiling of the initial recall tasks. Consequently:

- the result does **not** demonstrate cognitive accumulation;
- the result does **not** refute structured cognition, because the task is non-discriminating at ceiling;
- it establishes a strong long-context/full-history baseline;
- it invalidates raw recall under fully visible history as the sole primary efficacy endpoint;
- it exposes the provenance task-contract defect.

This is a useful negative result because it narrows the hypothesis rather than rewarding an easy benchmark.

## 6. Reproducibility and failure evidence

The provider experiment also exposed two implementation assumptions. First, the upstream endpoint required canonical `Accept` and AgentOS `User-Agent` headers. Second, execution from a fresh isolated checkout exposed an implicit repository import/PYTHONPATH dependency. Both were diagnosed and repaired before the successful run.

AgentOS treats such failures as durable negative knowledge. A failed route is not discarded simply because a later route succeeds: the failure, its context, diagnosis, repair, and validation receipt are retained so a replacement executor can avoid repeating known-bad paths. This mechanism is architecturally implemented but its efficacy under controlled executor replacement remains to be measured.

## 7. Cross-session execution observations

### 7.1 Historical observation

During AgentOS development, one long-lived conversation evolved from user-clocked `continue` interactions into extended inspect→act→verify→derive-next chains. In the strongest observed instances, more than twenty and later more than thirty tool/action steps occurred after a single user instruction before interruption or finalization.

Historical reconstruction does not identify a single causal trigger. Exact `/goal` syntax is neither necessary nor sufficient; GitHub persistence existed before mature execution; GitHub Actions strengthened machine-readable feedback but did not by itself establish goal semantics; Oracle strengthened bidirectional persistent execution but appeared after long-horizon behavior had already begun.

The best current explanation is joint emergence from stable goal semantics, broad termination criteria, accumulated context/IR, reliable multi-tool actions, persistent machine-readable state, verification feedback, and sufficient authority for reversible low-risk steps.

### 7.2 Transfer observation

The execution behavior was subsequently summarized into portable handoff/disposition contracts and used in fresh conversations. Fresh-session recovery has been observed informally: a new executor can recover project state, reconcile live repository state, derive a next action, and continue. However, the sustained execution depth has not consistently matched the strongest historical executor.

This observation motivates a useful decomposition. Cross-session continuity is not one variable. It contains at least:

- state recovery;
- goal recovery;
- next-action derivation;
- termination persistence / premature-finalization resistance;
- duplicate-work avoidance;
- failure avoidance;
- governance preservation;
- sustained action→receipt→next-action depth.

The observations in this section are **not** counted as controlled evidence for RQ1 or RQ2.

## 8. What remains falsifiable

The architecture becomes scientifically interesting only if it beats strong competing explanations. The next discriminating matrix is therefore pre-specified as follows.

| Condition | Persistent structure | Direct full history | Retrieval | Supersession/reconciliation |
|---|---|---|---|---|
| B0 task-local frozen model | No | No | No | No |
| B1 long-context/full history | No | Yes | No | Model must infer |
| B2 retrieval-only | No | No | Yes | No explicit semantics |
| B3 structured AgentOS cognition | Yes | No/controlled budget | Structured access | Yes |

Additional ablations remove supersession, reconciliation, failure knowledge, durable execution disposition, or governance separation one at a time.

The primary discriminating task families are pre-specified as:

- contradiction and supersession under many distractors;
- explicit provenance and trust selection;
- context-budget-constrained continuity;
- forgetting and later revival;
- unseen transfer requiring relations rather than verbatim recall;
- known-failure avoidance after executor replacement;
- incomplete-work continuation without repeating completed work;
- governance changes where capability and authority diverge;
- fresh-session executor replacement.

A positive AgentOS claim requires B3/full AgentOS to outperform B1 and B2 on pre-specified endpoints under the same model and authority envelope. Merely increasing available context is not sufficient evidence.

## 9. Statistical analysis plan

The completed seed-73129 deterministic series is a mechanism/harness result, not a population-level efficacy estimate. A discriminating efficacy series should use multiple frozen seeds and matched tasks across conditions. Reporting should include task-level outcomes, condition means, paired differences, confidence intervals, and effect sizes where meaningful. Provider stochasticity should be sampled with repeated runs even at temperature 0 unless deterministic execution is guaranteed by the provider.

Ceiling endpoints should not serve as the sole primary outcome. For binary or bounded task success, paired bootstrap confidence intervals or an appropriate paired categorical test can be reported across matched task instances; hierarchical analysis can be used if multiple seeds and task families create nested observations. Statistical choices must be fixed before inspecting the target comparison.

Evidence claims are promoted only through the following ladder:

**harness validated → mechanism observed → replicated → discriminates against strong baselines → survives ablation → transfers across executor/model replacement where claimed.**

## 10. Threats to validity

**Ceiling effects.** The first full-history condition saturates the initial benchmark and therefore cannot establish improvement.

**Metric-contract mismatch.** Initial source recall counted literal references that public prompts did not request.

**Provider drift.** `gemini-3.1-flash-lite` is a provider model reference rather than necessarily an immutable weight snapshot. Repeated series must preserve provider/model receipts and avoid interpreting alias drift as learning.

**Synthetic-world validity.** Project Meridian provides control and auditability but does not establish performance on real long-lived projects.

**Context leakage.** A host product may expose session/user context not represented in the experiment packet. Formal fresh-session trials must control supplied state as far as the host permits and document residual uncertainty.

**Tool and authority confounding.** A system with more tools or permissions can appear more intelligent. Capability and governance must remain fixed in cognitive comparisons.

**Executor/runtime dependence.** Very long single-turn action chains may depend partly on host runtime behavior. AgentOS correctness must not require a particular product's hidden scheduling semantics.

**Selection bias.** Successful recovery anecdotes cannot substitute for pre-specified fresh-session trials.

**Evaluator literalism.** Deterministic atom matching is auditable but may under-credit semantically correct paraphrases. Any semantic judge must be reported as a separate evaluator condition.

## 11. Supported and unsupported claims

### Supported by completed evidence

1. A controlled LCCB pack can physically separate public experience from evaluator-only labels.
2. The fixed-model provider harness executed successfully in an isolated external environment with preserved receipts.
3. Under the completed full-public-history condition, the initial non-provenance metrics are at ceiling and show zero measured age-100→1000 gain.
4. The initial later-age provenance score is not interpretable because the task did not require the evidence representation being scored.
5. The benchmark therefore needs discriminating tasks beyond raw full-history recall.
6. AgentOS has implemented system mechanisms for durable state separation, goal-level disposition, governance boundaries, failure preservation, and concurrent canonical workstream design; mechanism existence is not equivalent to efficacy.

### Not established by the present evidence

1. AgentOS structured cognition improves longitudinal capability relative to long context.
2. Structured cognition outperforms retrieval-only memory.
3. Fresh conversations reliably reproduce the strongest observed long-horizon execution behavior.
4. Cross-model replacement preserves equivalent cognitive capability.
5. Persistent failure knowledge measurably reduces repeated failures after replacement.
6. AgentOS improves real-world project outcomes.

These statements are deliberately left unsupported until the pre-specified discriminating experiments are completed.

## 12. Discussion

The first empirical result changes the interpretation of AgentOS in a productive way. If a model can answer a benchmark perfectly because the entire relevant history is directly visible, storing a structured representation has not yet demonstrated cognitive value. The meaningful problem begins when history is too large, contradictory, superseded, differently trusted, partially forgotten, distributed across workstreams, or detached from the current executor.

This suggests that persistent cognition should be evaluated less like a larger notebook and more like an operating state: what is currently true, why it is believed, what it replaced, which failed routes must not be repeated, what remains unfinished, and which actions are authorized now. Those semantics can in principle compress a large history into decision-relevant state. Whether they actually improve a fixed model is the empirical question LCCB is designed to answer.

The cross-session observations also expose a distinction between knowledge continuity and execution continuity. An executor may recover the correct state and know the next action yet still finalize prematurely because conversational answerability competes with goal completion. This motivates treating execution disposition itself as durable, testable state rather than assuming that memory recovery automatically produces long-horizon agency.

Finally, governance cannot be treated as a post-hoc safety layer. If accumulated cognition changes what the system can accomplish, experimental comparisons must ensure that gains are not merely permission gains. The architectural separation between capability and authority is therefore part of the scientific identification strategy as well as the safety design.

## 13. Conclusion

AgentOS proposes that a replaceable LLM executor can operate over durable, governed cognitive and execution state. The present evidence establishes the experimental substrate but does not yet establish the central efficacy claim. The first real fixed-model full-history experiment reaches ceiling and yields zero measured age-100→1000 gain, showing that the initial recall benchmark is too easy to distinguish structured cognition from visible history. A provenance-contract defect further demonstrates why benchmark semantics must match scoring semantics.

Rather than treating these outcomes as failed evidence, we use them to narrow the claim. AgentOS must earn its value where persistence requires structure rather than visibility: supersession, reconciliation, provenance, failure memory, unfinished-work continuity, context compression, governance preservation, and executor replacement. LCCB now provides a pre-specified path for testing those claims against full-history and retrieval baselines under a frozen model and authority envelope.

The strongest conclusion supported today is therefore methodological and architectural, not a claim of achieved machine cognitive growth: **persistent cognition becomes scientifically meaningful only when its structured state explains capability that access to history alone cannot explain.**

## Reproducibility record

The completed result reported in Section 5 is tied to GitHub Actions workflow run `32581330887`, experiment commit `11a910eeefd09f2a33a994c2bbef04c3831bdbe0`, seed `73129`, 1,000 events, ages `0,100,1000`, temperature `0`, three repeats, and artifact digest `sha256:96ca40f58c8f743dc53bd4eb7fe0ae9345d3d8b9306d3a675d235e4dbd942b8a`. Future results must be appended with their own immutable receipts rather than retroactively changing the interpretation of this series.
