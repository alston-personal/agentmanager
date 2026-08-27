# AgentOS Closure Reality

**Status:** active governance checkpoint  
**Date:** 2026-08-27

AgentOS has repeatedly produced strong ideas, specifications, prototypes, and partial implementations faster than those ideas become durable operating capabilities. This document defines the anti-drift discipline for that failure mode.

## Problem: Closure Gap

A capability is not complete because it was discussed, specified, prototyped, or even implemented once. The recurring failure pattern is:

```text
idea -> discussion -> spec -> prototype -> partial implementation
                                      \
                                       -> attention moves elsewhere
```

The missing tail is:

```text
integration -> verification -> real operation -> regression guard -> closure
```

The canonical machine-readable inventory is `.agent/closure/ledger.yaml`.

## Lifecycle

Every material capability, role/runtime promise, research result, or governance mechanism should converge to one explicit stage:

```text
DISCOVERED
  -> SPECIFIED
  -> PROTOTYPED
  -> IMPLEMENTED
  -> INTEGRATED
  -> VERIFIED
  -> OPERATING
  -> GUARDED
  -> CLOSED
```

`CLOSED` does **not** mean immutable. It means the current claim has an owner, implementation, integration evidence, verification evidence, real operating evidence, and regression protection, with no known closure gap remaining.

A later architecture change may legitimately move an item backward or supersede it, but the transition must be explicit.

## Evidence gates

The audit enforces minimum gates:

- `IMPLEMENTED` requires implementation evidence.
- `INTEGRATED` additionally requires integration evidence.
- `VERIFIED` additionally requires verification evidence.
- `OPERATING` additionally requires operating evidence.
- `GUARDED` additionally requires a regression guard.
- `CLOSED` must retain no known gaps.

Run:

```bash
python3 scripts/closure_audit.py --summary
python3 -m unittest tests.test_closure_audit -v
```

## No Silent Park

If a discussion produces a meaningful architecture hypothesis or work item that will not be completed immediately, it must not disappear into conversation history. Record at least:

- stable id;
- owner;
- current stage;
- evidence already obtained;
- known gaps;
- the condition or experiment required to advance it.

A parked item is valid. An unrecorded abandoned item is drift.

## Reality dimensions

Architecture review must ask two independent questions:

1. **Architecture Reality:** does the thing actually exist?
2. **Closure Reality:** did it reach the operational stage being claimed?

This prevents misleading declarations such as a role marked `active` when only its contract exists but no employee activation/runtime evidence exists.

## Initial audit findings

The first ledger deliberately includes both strong and weak examples.

### Near closure / guarded

- Documentation Reality Guard.
- Protected-branch authority boundary.

These have implementation, verification, operating evidence, and regression protection.

### Material closure gaps

- Agent Organization / Employee Runtime: role definitions and responsibility resolution exist, but durable employees, assignment/activation, per-agent memory, messaging, handoff, and lifecycle closure are not proven end-to-end.
- Per-agent durable memory: role documents define memory scope, while the current memory router remains project-scoped.
- Cognitive IR: research/prototype direction exists, but there is no canonical portable schema with repeatable cross-model continuation evidence.
- Cognitive Thread / HEAD / Return Stack: the idea has a conversation-level prototype but is not integrated into continuation runtime.
- Capability learning loop: the architecture is specified, while the first complete LayoutLib execution-to-canonical-learning closed loop still needs durable evidence.
- Chronicler: the role is defined/proposed but is not an operating employee.
- Publisher capability: a Matters publishing skill exists, but current organization runtime does not prove routine role-driven activation.

## Closure priority rule

Prioritize gaps by leverage, not novelty. A gap should move upward when closing it unlocks multiple existing capabilities.

Current hypothesis: restoring the **Agent Employee / Organization Runtime** is a high-leverage closure target because it can reactivate existing roles, skills, memory scopes, responsibility resolution, Chronicle maintenance, review, publication, and future work-thread ownership without inventing parallel systems.

This remains a hypothesis until the closure audit and a real end-to-end employee workflow prove it.

## Governance rule

Do not use `active`, `implemented`, or `complete` as interchangeable words.

- `active role contract` means the definition is valid.
- `implemented capability` means code/artifact exists.
- `operating capability` requires real runtime evidence.
- `closed capability` requires all closure gates.

Claims must use the narrowest justified stage.
