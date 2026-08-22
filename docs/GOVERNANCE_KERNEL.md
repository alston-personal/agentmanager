# AgentOS Governance Kernel

Status: experimental State Kernel v2 governance foundation.

This document describes the executable enforcement layer behind
`docs/GOVERNANCE_INVARIANTS.md`.

## Completion target

For the current v2 capability surface, governance is considered structurally
closed when all of the following hold:

1. there is one canonical capability-risk authority;
2. effects and risks can raise the minimum capability level even if a runtime
   under-declares itself;
3. capability profiles come only from a governance-owned registry;
4. unknown or under-governed capabilities fail closed or degrade to
   proposal/read-only;
5. high-impact approval binds to one exact intent;
6. external effects require an authorized intent and SideEffect Ledger entry;
7. side effects have idempotency, receipts, compensation lineage and durable
   append-only audit history;
8. governance learning may add controls, raise risk, or reduce authority
   automatically, but may not remove controls, lower risk, or increase
   authority without owner approval;
9. every currently known capability has an explicit inventory entry and
   evidence refs;
10. experimental capability code is not equivalent to production authority.

## Authority flow

```text
untrusted runtime / model / node / provider
        |
        | capability + requested operation
        v
ActionIntent
        |
        v
GovernanceRegistry        <- only governance owns capability profiles
        |
        v
GovernanceGate            <- level + effect floor + risk + controls
        |
        v
ActionAuthorizationGate   <- exact intent + optional owner approval
        |
        v
SideEffect Ledger         <- prepare / commit / fail / compensate
        |
        v
executor
        |
        v
receipt + durable audit
```

No runtime is allowed to provide its own `controls` set at authorization time.
A capability implementation is not an authority source.

## Effect-derived authority floors

The capability declaration cannot hide the real impact of an effect.

```text
canonical_state       -> at least COMMIT (L3)
durable_memory        -> at least COMMIT (L3)
cross_project         -> at least COMMIT (L3)
external_reversible   -> at least ACT (L4)
external_high_impact  -> at least HIGH_IMPACT (L5)
autonomous            -> at least AUTONOMOUS (L6)
```

If a provider claims `SYNTHESIZE` while declaring an external effect, the Gate
still requires ACT-level governance and denies the under-declared request.

## Current capability authority

`agent_core/governance_inventory.py` is the executable inventory. Current
intent is:

- `project.state.read`: allowed as read-only authority.
- `project.state.commit`: proposal-only until an explicit governed
  rollback/restore path is wired.
- `cognitive.synthesis`: allowed; output remains candidate cognition.
- `cognitive.promote.project`: governed COMMIT-level cognitive promotion.
- `cognitive.promote.cross_project`: governed COMMIT-level promotion with
  stronger independent-evidence controls.
- `work.continue.select`: allowed selection-only authority; no execution.
- `browser.gemini.shadow`: shadow-only; live browser effects are not yet wired
  through ActionAuthorization + SideEffect Ledger.
- `node.external.act`: proposal-only.
- `agent.autonomous.external`: proposal-only.

This is deliberate authority reduction, not a missing feature claim. Governance
may be complete while a capability remains disabled.

## SideEffect Ledger

External effects are separated from canonical state commits.

A side effect has:

- `side_effect_id`
- `intent_id`
- optional `work_id`
- kind / target
- immutable intent hash
- idempotency key
- status: `prepared | committed | failed | compensated`
- compensation reference
- execution or compensation receipt
- failure reason

`agent_core/side_effect_store.py` persists the latest record plus append-only
lifecycle events in SQLite. The idempotency key is unique at the durable store
boundary.

## Governance learning

`agentos.governance-experience/v1` records safety outcomes such as:

- near miss
- policy violation
- approval override
- false positive / false negative
- successful intervention
- rollback

Governance learning follows an asymmetric law:

> Governance may autonomously become more conservative; it may not
> autonomously grant itself more authority.

Automatic changes may add controls, increase risk classification or reduce
available authority. Removing controls, lowering risk classification, hiding an
effect, registering a new authority, or increasing authority requires explicit
owner approval through the Governance Registry.

## What this does not authorize

This governance foundation does **not** by itself enable:

- production State Kernel v2 deployment;
- live Gemini Web automation;
- generic node shell/filesystem control;
- Home/IoT actions;
- high-impact physical actions;
- autonomous recurring external action;
- cross-Realm data sharing or Universal One federation.

Those capabilities must enter the inventory with their actual effects and pass
the same gates before promotion.

## Prime laws

> Capability must never scale faster than governance.

> Ideas may scale quickly; authority must scale deliberately.

> Intelligence learns how to do more; governance learns when it must not.

> Governance may tighten itself, but may not self-expand authority.
