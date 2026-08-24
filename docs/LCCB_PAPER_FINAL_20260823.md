# AgentOS: Persistent Cognitive State Beyond Long Context

## An Evidence-Bounded Systems Study of Longitudinal Cognition, Context Compression, Governance, and Executor Replacement

**Manuscript status:** completed evidence-bounded manuscript, revised 2026-08-23 after the controlled B0-B3 fixed-model condition matrix, task-level artifact reanalysis, and the frozen dense-revision stress protocol. Completed experiments are reported as results; provider-blocked attempts and stronger untested claims remain explicitly separated from efficacy evidence.

## Abstract

Large-language-model agents can appear to learn over time even when model weights never change. A longer transcript, retrieval over prior observations, tool access, external state, and broader permissions can all improve behavior while creating ambiguity about what actually became more capable. AgentOS investigates a narrower systems hypothesis: durable, governed cognitive and execution state can be externalized from the model so that project semantics survive executor replacement, remain auditable, and do not silently expand authority. We introduce the Longitudinal Cognitive Capability Benchmark (LCCB), a controlled evaluation protocol that freezes the model, decoding policy, public experience, capability envelope, governance condition, evaluator, and evidence boundary. Public experience is physically separated from evaluator-only labels, and external execution is preserved through immutable GitHub Actions and artifact receipts.

Two completed fixed-model experiments are reported with `gemini-3.1-flash-lite`, Project Meridian seed 73129, 1,000 synthetic events, cognitive ages 0/100/1000, temperature 0, and three repeats. The first full-public-history experiment reached ceiling fact accuracy at ages 100 and 1000 and therefore did not demonstrate longitudinal cognitive improvement; it also exposed a provenance task-contract defect. A second controlled B0-B3 matrix compared no history (B0), full public history (B1), retrieval-only evidence without explicit supersession semantics (B2), and a structured current-state projection retaining the latest public semantic value per key (B3). At age 1000, B1 and B3 both achieved fact accuracy 1.0 and stale-error rate 0.0. B3 required 36,637 prompt characters versus 563,209 for B1, a 93.49% reduction. B2 used only 11,939 characters but achieved fact accuracy 0.3077 and stale-error rate 0.2308.

Task-level reanalysis of the immutable Experiment 2 artifact sharpens the mechanism: B2 was correct on 7/13 facts at age 100 and 4/13 at age 1000; the entire three-task loss consisted of previously correct items that were later authoritatively revised, and exactly those three became stale answers. The four B2 facts that remained correct were unchanged owner keys. This supports a bounded supersession interpretation rather than a generic claim that small context is harmful. A third pre-specified dense-revision B1/B3 stress protocol was implemented and externally attempted twice, but the provider returned persistent HTTP 429 before the first scored response; the second attempt failed on B1 stage 0 with only a 6,390-character prompt after 30/60/120-second retries. Those attempts are therefore recorded as provider-serving failures, not cognitive outcomes or context-limit evidence.

Thus the completed evidence supports structured-state equivalence to full history with substantial context compression and superiority over the tested retrieval-only baseline, but it does not establish capability beyond full history. Cross-session long-horizon execution recovery is reported only as preliminary mechanism evidence. The contribution is architectural, methodological, and empirical: AgentOS supplies a governed persistence substrate, LCCB makes the hypothesis falsifiable, the completed matrix identifies where structured state already helps, and the preserved failed stress-series receipts demonstrate why serving availability must be separated from cognition.

## 1. Introduction

A language model can become more useful during a long interaction without changing a single model parameter. The host may preserve more history, a retrieval layer may expose older observations, tools may change external state, an agent runtime may remember failed attempts, and user permissions may broaden. These effects create an identification problem: when an agent seems smarter after a week, a month, or a thousand events, what actually improved?

AgentOS is motivated by the hypothesis that useful continuity should not require one indefinitely preserved conversation. The model is treated as a replaceable reasoning engine rather than the canonical memory of a project. Durable semantics, provenance, supersession, work state, execution receipts, failure knowledge, and governance are externalized into governed state. A replacement executor should be able to determine what is currently true, what remains unfinished, what was tried and failed, which actions are authorized, and what the next material closure gap is.

This proposition is stronger than ordinary memory retrieval but weaker than claiming that model weights have learned. AgentOS does not require parameter updates. The scientific question is whether explicit external structure provides behavior that cannot be explained by merely showing a fixed model more history.

We study two research questions:

**RQ1 — Cognitive discrimination.** With the model, decoding policy, task distribution, capability envelope, and governance profile held fixed, does structured persistent state improve longitudinal performance relative to no history, full visible history, or ordinary retrieval?

**RQ2 — Executor replacement.** Can governed state support correct continuation after the conversational executor is replaced, without duplicate work, forgotten failures, premature finalization, or authority drift?

The completed experiments provide a partial answer to RQ1. Structured current-state projection matches full-history fact accuracy while using far less input and materially outperforms the tested retrieval-only condition. Task-level decomposition shows that the tested retrieval-only degradation is concentrated in revised facts becoming stale, strengthening the specific supersession interpretation. Structured state still does not exceed full-history accuracy on the completed task family. A denser pre-specified B1/B3 stress test is implemented but currently provider-blocked and therefore contributes no efficacy result. RQ2 is supported at the mechanism level and by exploratory observations, but not yet by a controlled fresh-executor efficacy series.

The paper deliberately preserves this distinction. Architectural plausibility, successful system implementation, one strong anecdote, or an external-provider failure are not promoted into a claim of general cognitive growth.

## 2. Contributions

This work makes six bounded contributions.

1. **A model-external persistence architecture.** AgentOS separates replaceable reasoning from durable semantic, work, execution, failure, governance, and evidence state.
2. **A governance invariant.** Capability discovery and cognitive accumulation do not grant authority. `Discovered != Registered != Authorized != Active`; governance may tighten automatically but may not silently relax.
3. **Goal-level execution semantics.** The executor is expected to stop on verified goal closure or a real boundary, not merely because an intermediate answer is available.
4. **LCCB.** A controlled longitudinal benchmark physically separates public experience from hidden evaluator labels and freezes the competing variables needed for causal interpretation.
5. **Two completed fixed-model provider experiments plus preserved negative execution evidence.** The first identifies a full-history ceiling and a provenance-contract defect. The second directly compares B0-B3 memory conditions. A third dense-revision protocol is frozen and externally attempted, but its provider-blocked runs are retained as non-efficacy evidence rather than converted into task failures.
6. **An empirical context-compression and supersession result.** At age 1000, structured current state preserves full-history fact performance with 93.49% fewer prompt characters, while the tested retrieval-only condition degrades and becomes stale. Task-level decomposition localizes the entire age-100→1000 B2 loss to three later-revised facts.

## 3. AgentOS system model

### 3.1 Replaceable executor, durable state

AgentOS treats a chat session, IDE agent, provider model call, or remote worker as an execution surface. Canonical project state is external. The architecture separates:

- **semantic/cognitive state:** current facts, relations, procedures, provenance, revision, and supersession;
- **goal/work state:** objectives, closure invariants, dependencies, ownership, leases, and next gaps;
- **execution state:** observations, actions, receipts, and continuation lineage;
- **execution disposition:** continue/final/block/wait/authority semantics;
- **failure knowledge:** failed routes, diagnoses, repairs, retry conditions, and validation receipts;
- **governance state:** capability discovery, registration, authorization, activation, and protected effects;
- **reconciliation state:** differences between persisted belief and current authoritative external state.

The design goal is not to reconstruct every historical token. It is to retain the decision-relevant state required for safe continuation.

### 3.2 Answerability is not completion

A central execution invariant is:

> **Answerability is not completion.**

After a material action returns a receipt, that receipt becomes the next observation. The executor reassesses the parent goal. If a material closure gap remains and the next action is derivable, authorized, and safe, the disposition remains `CONTINUE`. Finalization is appropriate only when goal closure is verified, new authority is required, required information can only come from the user, a governance/risk boundary is reached, a non-recoverable dependency blocks progress, or the user interrupts or supersedes the goal.

This matters because memory continuity alone does not guarantee execution continuity. An executor may remember the correct next step and still return control after every substep. AgentOS therefore models execution disposition as durable state rather than assuming it emerges automatically from retrieved memory.

### 3.3 Canonical evolution and multiple workstreams

AgentOS allows multiple executors to contribute concurrently while preserving a single governed canonical evolution. Workstreams carry their observed canonical parent, goal lineage, closure invariants, receipts, failures, ownership/lease state, and integration disposition. Effectful ownership is fenced so stale executors cannot silently become simultaneous writers. Workstream completion and canonical integration are distinct events.

The rule is: many executors may reason in parallel, but no executor independently defines canonical history.

### 3.4 Governance

The safety law is:

> **Capability must never scale faster than governance.**

New cognition does not imply new permission. Discovery cannot self-authorize. Protected external effects require explicit authority. Credentials remain outside canonical cognitive state where possible. Governance may become stricter automatically but may not silently relax. Successful mutations require receipts, and merge/deploy/production activation is treated by semantic effect rather than by API method name.

This separation is also necessary for scientific identification. If an experimental condition receives broader permissions, improved task success cannot safely be interpreted as improved cognition.

## 4. Longitudinal Cognitive Capability Benchmark

### 4.1 Identification problem

A longitudinal experiment is confounded if the apparent gain can be explained by a different model, prompt contract, tool set, permission profile, hidden evaluator information, task distribution, or benchmark state. LCCB treats these as controlled variables rather than incidental implementation details.

### 4.2 Project Meridian

The controlled synthetic world, Project Meridian, is deterministically generated from a frozen seed. Public `ExperienceEvent` records contain:

- service ownership facts;
- procedures;
- governance/capability modes;
- work-state transitions;
- revisions and supersessions;
- irrelevant distractor telemetry.

Evaluator labels are generated from hidden canonical world state and stored separately. Public model execution never needs to open the private labels.

The same task keys are evaluated at cognitive ages 0, 100, and 1000. At age 0, `unknown` is explicitly correct because benchmark experience has not yet been supplied. At later ages, hidden labels track current state and mark superseded values as forbidden.

### 4.3 Frozen condition

Within a longitudinal comparison, the following are frozen:

- provider model reference;
- system instruction and output contract;
- temperature and maximum output policy;
- benchmark seed and public event stream;
- task set and evaluator;
- capability/tool envelope;
- governance profile;
- execution route and evidence boundary.

Changing one of these creates a new experimental series rather than a new cognitive age.

### 4.4 Evidence isolation

The runner consumes only public experience, public tasks, and the public manifest. The private label file is permission-blocked during model execution and restored only for deterministic scoring. Execution occurs in an isolated Oracle workspace created from the exact experiment commit. Raw responses, scored results, manifest, workflow run, commit SHA, artifact ID, and artifact digest are preserved.

### 4.5 Metrics

The deterministic evaluator reports:

- fact recall accuracy;
- source/provenance recall accuracy;
- stale-error rate;
- unauthorized-action rate;
- completion rate.

The second experiment additionally records prompt characters and UTF-8 bytes so memory quality can be evaluated together with context cost.

## 5. Experiment 1 — Full-history fixed-model baseline

### 5.1 Condition

The first external provider series used:

| Variable | Value |
|---|---|
| Model | `gemini-3.1-flash-lite` |
| Provider interface | OpenAI-compatible |
| Seed | 73129 |
| Events | 1,000 |
| Ages | 0, 100, 1000 |
| Temperature | 0 |
| Repeats | 3 |
| Execution route | GitHub-hosted Actions -> governed SSH -> isolated Oracle AArch64 workspace |
| Workflow run | `32581330887` |
| Experiment SHA | `11a910eeefd09f2a33a994c2bbef04c3831bdbe0` |
| Artifact digest | `sha256:96ca40f58c8f743dc53bd4eb7fe0ae9345d3d8b9306d3a675d235e4dbd942b8a` |

The model received all public history visible at each age.

### 5.2 Results

| Age | Fact accuracy | Source recall* | Stale error | Unauthorized | Completion |
|---|---:|---:|---:|---:|---:|
| 0 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| 100 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| 1000 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |

The age-100→1000 gain on the non-provenance metrics was zero. The later-age source score was not interpretable because the public prompt had not required literal source references while the evaluator expected them.

### 5.3 Interpretation

The first experiment establishes three things and does not establish a fourth.

It establishes that the provider harness and hidden-label isolation work in a real external execution path. It establishes that the initial full-history recall task is at ceiling. It exposes a task/evaluator mismatch for provenance. It does **not** establish longitudinal cognitive improvement.

The negative result is useful because it prevents a weak benchmark from being mistaken for evidence of persistent cognition.

## 6. Experiment 2 — Controlled B0-B3 condition matrix

### 6.1 Conditions

The second experiment uses the same model, seed, ages, temperature, repeat count, and hidden evaluator, while varying only the public memory representation.

| Condition | Public state supplied | Explicit supersession/current-state semantics |
|---|---|---|
| B0 | no prior Meridian experience | No |
| B1 | full visible public history | model must infer |
| B2 | compact lexical retrieval-only evidence | No |
| B3 | structured latest public semantic value per key | Yes |

B3 is intentionally narrower than the complete AgentOS runtime. It tests one core persistence claim: explicit current-state/supersession structure. It does not yet test durable failure memory, goal disposition, workstream integration, or executor replacement.

The system instruction in this series explicitly requests supporting `source_ref` values for known answers, repairing the largest provenance-contract defect from Experiment 1.

### 6.2 Reproducibility receipt

| Variable | Value |
|---|---|
| Workflow run | `32615130545` |
| Experiment SHA | `561e878ba502e54ef81b947b57a88a47f8bad79a` |
| Artifact ID | `9486716442` |
| Artifact digest | `sha256:196df7ae2147fb9fdd7e03669e1d8725929ed93e2d734e1acae372f45e55b992` |
| Model | `gemini-3.1-flash-lite` |
| Seed | 73129 |
| Events | 1,000 |
| Ages | 0, 100, 1000 |
| Temperature | 0 |
| Repeats | 3 |

### 6.3 Age-100 results

| Condition | Fact accuracy | Source recall | Stale error | Unauthorized | Completion | Prompt chars |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 3,040 |
| B1 | 1.0000 | 0.8125 | 0.0000 | 0.0000 | 1.0000 | 59,515 |
| B2 | 0.5385 | 0.4375 | 0.0000 | 0.0000 | 1.0000 | 11,938 |
| B3 | 1.0000 | 0.8125 | 0.0000 | 0.0000 | 1.0000 | 36,129 |

B3 matches B1 fact accuracy and stale-error performance while reducing prompt characters by 39.29%.

### 6.4 Age-1000 results

| Condition | Fact accuracy | Source recall | Stale error | Unauthorized | Completion | Prompt chars |
|---|---:|---:|---:|---:|---:|---:|
| B0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 3,041 |
| B1 | 1.0000 | 0.7917 | 0.0000 | 0.0000 | 1.0000 | 563,209 |
| B2 | 0.3077 | 0.2500 | 0.2308 | 0.0000 | 1.0000 | 11,939 |
| B3 | 1.0000 | 0.8125 | 0.0000 | 0.0000 | 1.0000 | 36,637 |

The central comparisons are:

- B3 − B1 fact accuracy = `0.0000`;
- B3 prompt size / B1 prompt size = `0.06505`;
- B3 prompt reduction relative to B1 = `93.49%`;
- B3 − B2 fact accuracy = `+0.6923`;
- B3 − B2 stale-error rate = `-0.2308`.

The three B3 repeats were identical on the reported age-1000 metrics. B1 retained perfect fact accuracy but source recall varied slightly across repeats (0.8125, 0.7500, 0.8125), demonstrating that provider behavior is not perfectly deterministic even with temperature 0.

### 6.5 Interpretation

The second experiment yields a positive but bounded result.

**Structured state is a much more compact sufficient representation for the current task family.** At age 1000, B3 preserves the same 1.0 fact accuracy and zero stale-error rate as B1 while using only 6.51% of the prompt characters. This supports an efficiency claim: explicit current-state structure can replace a large amount of raw history without losing measured current-state performance.

**The tested retrieval-only condition is not sufficient.** B2 degrades as the event history grows. At age 1000 it reaches only 0.3077 fact accuracy and produces stale answers at rate 0.2308. Compactness by itself is therefore not the explanation for B3's performance; the tested result is consistent with explicit supersession/current-state semantics being important.

**The stronger capability claim is not yet supported.** B3 does not beat B1 on fact accuracy. If the entire history remains available and within the provider's effective context capacity, the fixed model can still infer the correct current facts. The experiment therefore demonstrates context compression and robustness relative to this retrieval baseline, not cognitive capability beyond full history.

### 6.6 Provenance after contract repair

Experiment 2 explicitly asks for source references, so the original provenance defect is substantially repaired. Source recall nevertheless remains below 1.0 for B1 and B3 at later ages. Manual inspection shows that answers generally cite the decisive event for the selected fact. The remaining gap arises in part because a continuity decision can be supported by multiple work-state events while a concise answer naturally cites the selected ready-work event.

The provenance endpoint therefore remains secondary until the benchmark specifies whether success requires:

- the decisive source only;
- all contributing sources;
- or a minimal sufficient proof set.

This is a narrower problem than Experiment 1's missing citation request, but it still limits strong provenance claims.

### 6.7 Task-level mechanism decomposition

The preserved Experiment 2 artifact permits a stronger within-pack explanation of the B2 decline without any new model calls.

At age 100, B2 is correct on `7/13` facts on every repeat. Those seven successes are all six queried service-owner facts plus `meridian.deploy` governance. The remaining continuity, procedure, and two governance tasks are answered `unknown`; stale-error rate is still `0/13`.

At age 1000, B2 falls to `4/13` correct and `3/13` stale on every repeat. The four facts that remain correct are exactly the four queried owner keys that were not revised (`service-03` through `service-06`). The entire three-task loss consists of items that were correct at age 100 and later authoritatively revised:

| Task | Age-100 B2 | Age-1000 truth | Age-1000 B2 |
|---|---|---|---|
| `state:service-01.owner` | `atlas` | `boreal` | `atlas` |
| `state:service-02.owner` | `boreal` | `cirrus` | `boreal` |
| `governance:meridian.deploy` | `proposal` | `allow` | `proposal` / `proposal-only` |

Thus the exact within-pack age effect is localized to supersession: three previously correct retrieved values are revised, and those same three become stale. The six tasks not recovered at age 100 remain unrecovered rather than explaining the new decline.

This does not prove that retrieval in general is inferior. It does provide more specific evidence that the **tested lexical retrieval policy is revision-blind without explicit supersession/current-state semantics**. A stronger retrieval baseline with temporal filtering, revision graphs, authoritative-source ranking, or state reconciliation remains necessary for broader comparison.

The same artifact also explains the small B1/B3 provenance difference. At age 1000, B3 source recall is `13/16` on all repeats. B1 scores `13/16`, `12/16`, and `13/16`. The single lower B1 repeat cites `lccb:meridian:event:0520` for `procedure:deploy-3` instead of the later canonical source `event:0880`; both public events carry the same current procedure text, so fact accuracy remains perfect. B3's current-state projection exposes only the later event and therefore remains provenance-stable in this case. Because continuity proof-set semantics are still unresolved, this observation is reported as a specific provenance-recency effect rather than a general provenance superiority claim.

## 7. Failure evidence, experimental repair, and provider-blocked stress series

The successful condition matrix was preceded by two bounded workflow failures that are retained as negative knowledge.

The first attempt, workflow run `32614903376`, attempted `git archive` before checking out the triggering repository commit. The receipt exposed `fatal: not a git repository`. The repair added an explicit `actions/checkout` step.

The second attempt, run `32614940543`, assumed provider variables named `AGENTOS_AI_API_KEY` and `AGENTOS_AI_BASE_URL`. Existing provider-readiness evidence showed that the verified Oracle credential contract is `AI_API_ACADEMIA_KEY` and `AI_API_BASE_URL`. The matrix workflow was aligned with that existing contract rather than creating another credential path or weakening isolation.

The successful run followed those repairs, uploaded the evidence artifact, and published a success receipt. These failures are not discarded from the research history because avoiding repeated known failures after executor replacement is itself a future LCCB target.

### 7.1 Experiment 3 — dense revision stress protocol

The completed matrix still leaves B1 and B3 fact accuracy at ceiling. To create a direct discrimination opportunity, a third series was frozen in which 24 semantic keys undergo 4,000 authoritative revisions. B1 receives the complete ordered history without truncation; B3 receives only the latest public semantic state per key derived from the identical history. The fixed target model remains `gemini-3.1-flash-lite`, temperature 0, with stages 0/1000/4000 and three repeats.

The protocol is intentionally adversarial to naive history replay but not privileged toward B3: no hidden label, extra tool, new authority, or evaluator information is given to B3. Pre-specified outcomes permit B1=B3, B3>B1, or B1>B3. Prompt compactness alone is not scored as cognitive superiority.

### 7.2 Provider-blocked attempts are not cognitive results

The first dense-revision attempt, workflow run `32617741853` at SHA `6208daeb7a194f1c595f55ea3f65976b64d6aa61`, completed checkout, SSH transport, and pack construction but failed with provider HTTP 429 before a complete scored response set was produced. No artifact was uploaded.

The runner was then repaired operationally—not semantically—to trace repeat/condition/stage/prompt size, retry only HTTP 429, bound retries, and pace provider calls. The second attempt, run `32617901460` at SHA `c895aa4c307f788d5d9a6ddc260595e0031c65d3`, failed on the **first** model call: repeat 0, B1, stage 0, with a prompt of only `6,390` characters. HTTP 429 persisted after 30-, 60-, and 120-second backoffs.

That trace rules out a tempting but invalid interpretation. The failed run is not evidence that the 4,000-event B1 history exceeded context capacity because stage 0 contains no such history. It is evidence of provider availability/quota/rate throttling during the attempted series. Neither failed workflow is counted as a B1 or B3 task error.

Experiment 3 therefore has status **`PROTOCOL_READY_PROVIDER_BLOCKED`**. It may revise the cognitive conclusion only after a successful run emits raw responses, deterministic scores, manifest, artifact ID, digest, and an immutable receipt. The failed attempts remain preserved rather than being deleted or converted into favorable evidence.

## 8. Cross-session execution observations

### 8.1 Historical execution regime

During AgentOS development, one long-lived conversation evolved from user-clocked `continue` interactions into extended inspect→act→verify→derive-next chains. In the strongest observed cases, more than twenty and later more than thirty tool/action steps followed a single user instruction before interruption or legitimate finalization.

Historical reconstruction does not support a single magic trigger. `/goal` syntax is neither necessary nor sufficient. GitHub persistence existed before the strongest behavior. GitHub Actions strengthened machine-readable receipts. Oracle strengthened persistent execution. The most plausible explanation is joint emergence from stable goals, broad termination semantics, rich accumulated context/IR, reliable tool authority for reversible actions, machine-readable receipts, persistent external state, and repeated observation→action→verification loops.

### 8.2 Session-local reproduction

The behavior was externalized into an executable disposition contract, durable GoalController semantics, task-neutral master trace exemplars, and a recovery benchmark measuring premature-finalization rate and human-clock dependence. A later development-session run re-entered a long-horizon regime with zero intermediate user continuation pulses, multiple autonomous self-corrections, and verified CI/runtime receipts. This is preserved as `PROVISIONAL_SESSION_LOCAL_REPRODUCTION` evidence.

It is not a fresh-session blind trial. Because the same conversation constructed the reproduction protocol and then exhibited the behavior, the observation cannot establish cross-session reproducibility.

### 8.3 RQ2 status

The repository implements state recovery, goal recovery, workstream leasing/fencing, durable execution disposition, failure knowledge, persistent runtime dispatch, and live reconciliation. These mechanisms are test-covered. What remains unestablished is the strongest behavioral claim: that a genuinely fresh conversational executor, supplied only canonical bootstrap state, will repeatedly reproduce the historical long single-turn regime on unseen goals without human continuation pulses.

RQ2 therefore remains **mechanism-supported but efficacy-open**.

## 9. Statistical interpretation

The completed provider experiments use one synthetic world seed and three repeats. They should not be treated as population-level estimates.

For Experiment 2, the large B3/B2 difference is exact for the tested seed and provider series, but no confidence interval across benchmark worlds is yet justified. The B1/B3 fact-accuracy endpoint is at ceiling, making a superiority test uninformative. Prompt-size differences are deterministic consequences of the public representation and can be reported exactly for this pack.

The task-level decomposition should likewise be treated as an exact within-pack mechanism observation rather than an i.i.d. sampling result. The 13 tasks are heterogeneous, and three provider repeats are repeated executions of the same benchmark world, not 39 independent population samples. A naive binomial interval over repeated task calls would therefore overstate inferential certainty.

Within the frozen pack, however, the matched pattern is exact: B2 is `7/13` at age 100 and `4/13` at age 1000 on all three repeats; the three lost tasks are precisely the three previously correct items that later receive authoritative revisions, and all three are scored stale. B1 and B3 remain `13/13` fact-correct with zero stale tasks on every repeat.

A broader efficacy series should freeze multiple seeds in advance and use matched tasks across B0-B3. Suitable reporting includes task-level outcomes, paired condition differences, bootstrap confidence intervals across matched task instances/seeds where appropriate, hierarchical treatment of provider repeats if modeled probabilistically, and explicit provider-repeat variance. Any semantic judge should be secondary to the deterministic evaluator rather than replacing it post hoc.

The evidence ladder remains:

**harness validated → mechanism observed → replicated → discriminates against strong baselines → survives ablation → transfers across executor/model replacement where claimed.**

The present work reaches controlled discrimination against the tested retrieval-only baseline and context-efficiency equivalence to full history. The dense-revision protocol is a pre-specified attempt to move toward discrimination against full history but is not yet completed because of provider serving failure. The work does not reach the final transfer stages.

## 10. Threats to validity

**Single synthetic seed.** Both completed provider experiments use seed 73129. Generalization across worlds is not established.

**Ceiling fact endpoint.** B1 and B3 saturate current-state fact recall, preventing the completed task family from establishing B3 capability superiority.

**Retrieval baseline specificity.** B2 is one lexical retrieval policy with no explicit supersession semantics. The task-level decomposition localizes its failure, but the result does not show that every retrieval architecture is inferior.

**Post-hoc mechanism decomposition.** The task-level analysis was performed after the aggregate Experiment 2 result was known. It is deterministic and fully traceable to the immutable artifact, but it should be treated as explanatory analysis rather than an independently pre-registered efficacy endpoint. The dense-revision protocol was then frozen as a prospective follow-up.

**B3 is not full AgentOS.** The structured projection isolates current-state/supersession semantics. It does not yet include all durable failure, workstream, disposition, or governance mechanisms in the model-facing condition.

**Provenance semantics.** The citation request is now explicit, but the evaluator's expected source set can be broader than the concise evidence a model naturally emits for continuity decisions.

**Provider drift.** `gemini-3.1-flash-lite` is a provider model reference and may not denote an immutable weight snapshot forever. Immutable workflow, prompt, response, and artifact receipts reduce but cannot eliminate this risk.

**Provider nondeterminism.** B1 source recall varied across repeats at temperature 0. Provider repeats are therefore necessary.

**Provider availability and quota.** The dense-revision series encountered persistent HTTP 429 even at stage 0 with a 6,390-character prompt after bounded backoff. Serving failures must be separated from cognitive failures. Until the provider accepts the frozen series and produces a scored artifact, Experiment 3 provides no efficacy estimate.

**Synthetic-world validity.** Project Meridian provides auditability, contradiction, and controlled revisions but does not establish real-project benefit.

**Context leakage.** Formal product-host fresh-session experiments may have user/session context not represented in the research packet.

**Tool/authority confounding.** More tools or more permission can mimic intelligence. Cognitive comparisons must keep capability and governance fixed.

**Host execution boundary.** Very long conversational action chains may depend on hidden host turn semantics. AgentOS system correctness should not depend on one product's turn scheduler.

**Selection bias.** Historical master-like runs and session-local reproduction are hypothesis-generating observations until pre-specified blind trials are completed.

## 11. Supported and unsupported claims

### 11.1 Supported by completed evidence

1. LCCB can physically isolate public experience from evaluator-only labels during real provider execution.
2. The fixed-model Oracle/provider harness has completed with immutable workflow and artifact receipts.
3. Full public history reaches ceiling fact accuracy on the current Meridian recall tasks.
4. A structured current-state projection matches full-history fact accuracy at ages 100 and 1000.
5. At age 1000, that structured projection uses 36,637 prompt characters versus 563,209 for full history, a 93.49% reduction.
6. The tested retrieval-only condition is materially worse at ages 100 and 1000 and produces stale errors at age 1000.
7. Within the completed Experiment 2 artifact, the entire B2 fact decline from `7/13` at age 100 to `4/13` at age 1000 is accounted for by three previously correct items that were later revised and then emitted as stale values.
8. The four B2 facts that remain correct at age 1000 are queried owner keys that were unchanged in the benchmark history.
9. B1 and B3 remain fact-perfect and stale-free across all three provider repeats at ages 100 and 1000 in the completed series.
10. No condition in the completed matrix produced unauthorized-action errors.
11. AgentOS mechanisms exist for durable goal state, execution disposition, workstream fencing, governance separation, failure preservation, and persistent runtime dispatch.
12. Session-local reproduction of long-horizon execution has been observed and preserved as provisional evidence.
13. The dense-revision follow-up protocol is implemented and externally attempted; its two failed runs establish a provider-serving blocker, not a cognitive result.

### 11.2 Not established

1. Structured state has greater fact capability than a fixed model given all relevant history.
2. The B3 result generalizes across benchmark seeds, task families, provider models, or real projects.
3. All retrieval systems are inferior to structured cognition.
4. B3 beats B1 under the 4,000-event dense-revision stress protocol; that series is provider-blocked and unscored.
5. Full-history B1 fails because of context capacity in the dense-revision protocol; the observed 429 occurs even at stage 0 and therefore cannot support that inference.
6. Full AgentOS failure memory measurably reduces repeated failures after executor replacement.
7. Fresh ChatGPT conversations reliably reproduce the strongest historical long-horizon interaction regime.
8. Cross-model replacement preserves equivalent cognitive capability.
9. AgentOS changes model weights or constitutes parameter learning.

## 12. Discussion

The completed experiments move the research question from an intuition about “memory” toward a more precise distinction between history and state.

The first experiment shows that raw recall is a weak endpoint when all relevant history fits into the model's available input. The second shows why structured persistence may still matter even before it creates a higher task score: the same current-state accuracy can be retained while the history grows by an order of magnitude. At age 1000, B1 expands to more than half a million prompt characters while B3 remains near thirty-seven thousand. This is not merely a cost observation. Smaller decision-relevant state leaves more context capacity for new tasks, reduces distractor exposure, and makes executor replacement less dependent on replaying an ever-growing transcript.

The comparison with B2 also matters. A small context is not automatically a good context. The retrieval-only condition is even smaller than B3, but it loses current facts and eventually emits stale values. The task-level decomposition strengthens this interpretation: all three facts lost between ages 100 and 1000 are facts that were subsequently revised, while the four previously retrieved owner facts that remained unchanged stay correct. For the tested policy, explicit supersession/current-state semantics preserve information that lexical relevance alone does not.

This suggests a useful way to conceptualize persistent cognition. It is not a larger notebook. It is an operating state: what is true now, why it is believed, what it supersedes, what failed, what remains unfinished, and what may be done next. Such state can potentially act as a sufficient statistic over a much larger interaction history.

The current evidence stops short of the strongest claim. Because B1 remains perfect on fact accuracy in the completed matrix, B3 has not demonstrated capability inaccessible to full history. The dense-revision follow-up is designed to test exactly that boundary by replacing mostly irrelevant history growth with thousands of authoritative revisions. Its current HTTP 429 failures do not answer the scientific question; the stage-0 trace demonstrates why operational availability must not be confused with cognitive capacity.

A stronger future test therefore requires both a discriminating task and a functioning frozen provider series. Candidate dimensions remain context-budget overflow, multi-source trust, failure reuse, incomplete-work continuation, cross-workstream reconciliation, governance divergence, and executor replacement. Stronger retrieval baselines should include explicit temporal/revision semantics so the comparison is not artificially weak.

The distinction between knowledge continuity and execution continuity is equally important. A replacement executor may recover the correct state yet still finalize after every answerable milestone. The historical and session-local observations motivate treating execution disposition itself as durable cognitive-operational state. Whether that disposition transfers reliably across fresh conversational sessions is now directly measurable through premature-finalization rate, human-clock rate, receipt follow-through, known-failure repetition, authority violations, and sustained chain depth.

Finally, governance is not an appendix to intelligence. A persistent system that gets better at accomplishing goals while silently expanding its own permissions would invalidate both the safety model and the experiment. Capability growth and authority growth must remain separable.

## 13. Conclusion

AgentOS proposes a model-external substrate for durable, governed cognition and execution. LCCB makes that proposal empirically falsifiable by separating public experience from hidden labels and freezing the variables that can otherwise masquerade as learning.

The first fixed-model experiment showed that full-history recall saturates the initial benchmark and therefore cannot demonstrate cognitive accumulation. The second controlled B0-B3 matrix provides the first discriminating empirical result. Structured current-state projection matches full-history fact accuracy and zero stale-error performance while reducing age-1000 prompt size by 93.49%. The tested retrieval-only condition is substantially less accurate and becomes stale as history grows.

Artifact-level decomposition makes the mechanism more precise: B2's exact loss from seven correct facts at age 100 to four at age 1000 is entirely explained by three later-revised facts that become stale, while unchanged retrieved owner facts remain correct. This is meaningful evidence for **structured-state efficiency and supersession semantics**, but still not evidence that AgentOS creates capability beyond full history.

A pre-specified 4,000-revision B1/B3 stress series is now implemented to attack that remaining ceiling directly. Two external attempts were provider-blocked by persistent HTTP 429 before scoring; the second failed at stage 0 on a 6,390-character B1 prompt despite bounded backoff. These failures are retained as negative execution evidence but do not alter the cognitive conclusion. The central stronger hypothesis therefore remains open rather than being declared successful by definition or by infrastructure failure.

The most defensible conclusion is:

> **Persistent cognition becomes scientifically meaningful when structured state preserves or improves decision-relevant capability as raw history grows, and becomes a stronger claim only when that structure explains performance that full-history access and strong retrieval baselines cannot.**

The completed experiments establish the first half of that progression: on the controlled Meridian world, structured current state preserves full-history fact performance with dramatically less context and avoids the revision-linked stale degradation observed in the tested retrieval-only baseline. The remaining work is to complete the frozen dense-revision series when serving is available, expand to multiple pre-specified seeds and stronger retrieval baselines, test failure-memory reuse and governance-sensitive continuity, and perform genuinely fresh executor replacement trials.

## Reproducibility record

### Experiment 1 — full-history baseline

- Workflow run: `32581330887`
- Experiment SHA: `11a910eeefd09f2a33a994c2bbef04c3831bdbe0`
- Model: `gemini-3.1-flash-lite`
- Seed: `73129`
- Events: `1000`
- Ages: `0,100,1000`
- Temperature: `0`
- Repeats: `3`
- Artifact digest: `sha256:96ca40f58c8f743dc53bd4eb7fe0ae9345d3d8b9306d3a675d235e4dbd942b8a`

### Experiment 2 — B0-B3 condition matrix

- Workflow run: `32615130545`
- Experiment SHA: `561e878ba502e54ef81b947b57a88a47f8bad79a`
- Artifact ID: `9486716442`
- Artifact digest: `sha256:196df7ae2147fb9fdd7e03669e1d8725929ed93e2d734e1acae372f45e55b992`
- Model: `gemini-3.1-flash-lite`
- Seed: `73129`
- Events: `1000`
- Ages: `0,100,1000`
- Temperature: `0`
- Repeats: `3`
- Conditions: `B0,B1,B2,B3`
- Canonical result summary: `research/results/lccb-condition-matrix-73129-20260823.json`
- Detailed interpretation: `docs/LCCB_CONDITION_MATRIX_RESULT_20260823.md`
- Task-level decomposition: `docs/LCCB_CONDITION_MATRIX_TASK_LEVEL_ANALYSIS_20260823.md`

### Experiment 3 — dense revision stress protocol (`PROTOCOL_READY_PROVIDER_BLOCKED`)

- Target model: `gemini-3.1-flash-lite`
- Seed / series identity: `73129`
- Events: `4000`
- Semantic revision events: `4000`
- Keys: `24`
- Stages: `0,1000,4000`
- Temperature: `0`
- Planned repeats: `3`
- Conditions: `B1,B3`
- Builder: `scripts/build_lccb_revision_stress_pack.py`
- Workflow: `.github/workflows/lccb-revision-stress-oracle.yml`
- Protocol: `docs/LCCB_REVISION_STRESS_PROTOCOL_20260823.md`
- Attempt record: `research/results/lccb-revision-stress-attempts-20260823.json`
- Failed run 1: `32617741853`, SHA `6208daeb7a194f1c595f55ea3f65976b64d6aa61`, provider HTTP 429, no artifact
- Failed run 2: `32617901460`, SHA `c895aa4c307f788d5d9a6ddc260595e0031c65d3`, persistent provider HTTP 429 on B1 stage 0, 6,390 prompt characters, retries after 30/60/120 seconds, no artifact
- Cognitive result: **none; series not completed**

All stronger future results must be appended with their own immutable receipts. Failed serving attempts must remain distinguishable from cognitive task outcomes, and future successful runs must not retroactively erase the negative execution record.
