# AgentOS Governance Invariants

Status: normative architecture constraints for State Kernel v2 and all future Cognitive Kernel capabilities.

## Prime law

> **Capability must never scale faster than governance.**
>
> 能力越強，治理至少要同等變強；任何新增能力若提高自主性、影響範圍、不可逆性、資訊權限、持久性、跨專案傳播或推理權重，必須同時提高相應的驗證、授權、可追溯、隔離、回滾/補償、撤銷與人工介入能力。

This is not a product slogan. It is a release invariant.

A capability that violates this law is incomplete and must not be promoted to a higher-trust or production role.

## Governance dimensions

Every capability change must be evaluated across at least these dimensions:

1. **Authority** — what can the capability read, propose, mutate, commit, or trigger?
2. **Blast radius** — how much project, user, infrastructure, money, data, or external state can one failure affect?
3. **Reversibility** — can the effect be rolled back, or does it require compensation / human recovery?
4. **Autonomy** — can the system act without an explicit user turn or approval?
5. **Persistence** — can output become durable memory, canonical state, policy, or future retrieval input?
6. **Propagation** — can one agent's conclusion influence other agents, projects, devices, or long-term memory?
7. **Opacity** — how difficult is it to explain why an action, promotion, merge, or synthesis occurred?
8. **Uncertainty** — how much inference, ambiguity, untrusted input, or model judgment is involved?

Governance must strengthen monotonically as any of these dimensions increase, but controls are effect-aware rather than one universal checklist.

## Required governance controls

Depending on capability risk and effect domain, controls include:

- least-privilege scoped principals and capabilities;
- proposal-before-commit semantics;
- State Kernel validation and stale/conflict checks;
- provenance and source trust labels;
- immutable audit journal and receipts;
- idempotency and exact task/lease fencing;
- bounded StateView/context exposure;
- reversible state commits;
- side-effect prepare/commit/compensate lifecycle;
- explicit approval gates for high-impact actions;
- rate, scope, budget, and time limits;
- circuit breakers / kill switches;
- safe degraded modes when dependencies fail;
- independent verification for high-risk synthesized conclusions;
- ability to revoke credentials, runtimes, memories, and policies;
- human-readable explanation of current authority and pending effects.

## Cognitive Kernel rules

The Cognitive Kernel may retrieve, associate, abstract, brainstorm, analogize, synthesize, compact, re-synthesize, and generate hypotheses. These abilities do not grant truth authority.

The following rules are mandatory:

1. **Inference is not fact.** A synthesized insight starts as a candidate, not durable truth.
2. **Memory is not canonical state.** Retrieved or promoted memory cannot directly mutate Project HEAD.
3. **Synthesis must retain provenance.** New conclusions preserve links to supporting and contradicting evidence.
4. **Contradictions must survive.** Conflicting evidence may not be silently summarized away.
5. **Confidence is explicit.** Important synthesized knowledge carries confidence/validation state rather than rhetorical certainty.
6. **Promotion is governed.** Working -> Project -> Cross-project memory promotion requires stronger evidence as persistence and propagation increase.
7. **Cross-project influence requires stricter gates.** L3 knowledge has wider blast radius than project-local memory and therefore requires stronger validation.
8. **Supersession is immutable and auditable.** New knowledge may supersede old knowledge, but history and reasons remain inspectable.
9. **Autonomous re-synthesis does not imply autonomous action.** A new insight can create a proposal or review WorkItem; it cannot silently trigger high-impact external effects.
10. **Compaction may reduce prompt material, not provenance.** Meta-synthesis must remain traceable through immutable knowledge lineage to original ExperienceEvents or durable evidence anchors.
11. **A synthesizer cannot self-promote.** Model output claiming validated/project/cross-project authority is normalized back to Working/candidate until deterministic promotion gates pass.
12. **Re-synthesis is reconsideration, not mutation.** New contradiction, supersession, or analogy may schedule cognitive work but cannot directly rewrite durable memory.
13. **Source credentials are not experience.** Tokens, cookies, authorization headers and browser login material may not enter ExperienceEvent, memory, synthesis, or canonical state.
14. **Shadow before promotion.** A new real-world source adapter must first operate read-only/shadow and demonstrate bounded, idempotent, provenance-preserving ingestion before durable promotion is enabled.
15. **Third-party bridge authority stays bounded.** Browser/IDE/agent bridges are transports/runtimes; their session state and internal automation never become AgentOS authority.

## Capability ladder

```text
Level 0  Observe / read
         governance: authentication + provenance

Level 1  Retrieve / summarize / synthesize
         governance: source tracking + confidence + contradiction retention

Level 2  Propose state or memory changes
         governance: typed proposal + validation + reviewability

Level 3  Commit low-risk canonical state
         governance: scoped principal + CAS/conflict checks + audit + rollback

Level 4  Execute reversible external actions
         governance: idempotency + receipts + bounded scope + compensation

Level 5  Execute high-impact / irreversible actions
         governance: explicit approval or independently enforced policy gate,
                     strongest audit, circuit breaker, and minimal privileges

Level 6  Autonomous recurring / cross-project cognition or action
         governance: continuous policy enforcement, budgets, anomaly detection,
                     revocation/kill switch, independent verification, and
                     human override must exist before enablement
```

A subsystem may not move up the capability ladder before corresponding effect-appropriate governance controls exist and are tested.

## Fail-closed rule

When governance state is unknown, validation is unavailable, provenance is incomplete, lineage is broken/cyclic, approval cannot be verified, or a side-effect receipt is ambiguous:

> **Do not silently increase authority. Fail closed or degrade to proposal/read-only mode.**

Availability is never a justification for bypassing a required governance gate.

## Separation of powers

Where practical, high-impact flows should avoid letting one model/runtime both propose and authorize its own durable or external effects.

```text
Agent/runtime
  -> proposal
  -> independent policy / validator / human gate
  -> State Kernel / Cognitive Promotion Gate / Side-effect Executor
  -> commit/promotion + receipt/lineage
```

## Release gate

Every new AgentOS feature must answer:

```text
What new capability is being added?
What new authority does it gain?
What is the worst credible failure/blast radius?
What governance control is added at the same time?
How is the decision/action audited?
How is it stopped, revoked, rolled back, superseded, or compensated?
What happens when governance dependencies fail?
Can resulting knowledge/actions be traced to original sources?
Are source credentials/secrets excluded from cognitive state?
```

If these questions cannot be answered, the capability remains experimental and must not be promoted.
