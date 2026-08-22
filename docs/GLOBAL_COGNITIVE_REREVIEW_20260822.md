# AgentOS Global Cognitive Re-review — 2026-08-22

Status: experimental architecture review checkpoint. This document does not grant authority or activate production features.

## Purpose

After Governance Foundation / authority closure, re-review the existing AgentOS v2 system as one connected system rather than as isolated modules. The goal is to find missing cross-kernel relationships, stale assumptions, contradictions, and work that should resurface.

This review does **not** add product scope. It re-associates what already exists.

## New synthesis: four independent axes

A central result of the re-review is that several concepts previously risked being conflated:

```text
Importance   = is this worth doing?
Urgency      = how soon does it matter?
Readiness    = can it be worked on now?
Authority    = is it permitted to execute?
```

These are independent.

A task may be Q1 and ready but still be `proposal` or `shadow` because governance does not authorize execution. Priority pressure must never manufacture authority.

Epistemic confidence is a fifth, separate axis for knowledge rather than work:

```text
Confidence != Importance != Urgency != Readiness != Authority
```

## Cross-kernel re-association findings

### Fixed during this review

1. **Cognitive promotion -> Governance Registry**
   - Previous state: durable promotion accepted caller-supplied `governance_controls`.
   - Conflict: callers must not self-issue permission evidence.
   - Correction: durable project/cross-project promotion now resolves authority from the governance-owned registry.

2. **Priority Attention -> Governance Authority**
   - Previous state: priority understood blocker readiness but not governance mode.
   - Failure mode: a Q1 item could appear `do_now` even when only shadow/proposal authority existed.
   - Correction: priority snapshots now carry independent `authority_mode`; attention may resurface a task but cannot promote execution authority.

### Still missing / intentionally constrained

3. **Deferred Packet -> Durable Deferred Registry**
   - Current state: the IR and dynamic resurfacing policy exist, but there is no durable registry/query surface yet.
   - Consequence: unfinished work is representable but not yet reliably discoverable after long context drift.

4. **Dynamic Priority -> Work Graph selection**
   - Current state: Work Graph selects by static integer priority, dependency readiness, Project HEAD and stable ID.
   - Missing edge: dynamic importance/urgency/resurfacing is not yet the source of Work Graph scheduling priority.

5. **Work dispatch -> Governance Registry / ActionAuthorization**
   - Current state: Work Graph only selects; live dispatch is not enabled.
   - Required before dispatch: capability resolution and authorization must occur after selection and before execution.

6. **State commit -> governed rollback/restore**
   - Current state: immutable lineage, CAS and conflict detection exist.
   - Missing edge: explicit governed restore path.
   - Authority remains proposal-only.

7. **Gemini Browser Worker -> ActionAuthorization -> SideEffect Ledger**
   - Current state: Browser Worker contract exists and deterministic tests pass.
   - Missing edge: live browser action route has not been bound through intent authorization + SideEffect Ledger.
   - Authority remains shadow-only.

8. **Capability implementation -> automatic inventory coverage**
   - Current state: governance inventory is explicit and evidence-backed, but maintained manually.
   - Risk: a future new capability surface could exist before being added to the inventory.
   - Desired invariant: unregistered capability must remain unreachable/fail closed; CI should detect capability surfaces that lack reviewed registry entries where feasible.

## Re-prioritized matrix

Thresholds: importance >= 0.60, urgency >= 0.60.

| Item | Importance | Urgency | Drift/day | Quadrant | Readiness | Authority | Decision |
|---|---:|---:|---:|---|---|---|---|
| Durable Deferred Registry + pending query | 0.95 | 0.72 | +0.004 U | Q1 | ready | proposal until storage/CLI governance reviewed | **resurface now** |
| Wire dynamic Priority into Work continuation | 0.95 | 0.68 | +0.003 U | Q1 | ready | selection only | **resurface now** |
| Governed State rollback/restore | 0.97 | 0.56 | +0.004 U | Q2, near Q1 | ready | proposal | protect / next |
| Capability inventory coverage enforcement | 0.92 | 0.58 | +0.003 U | Q2, near Q1 | ready | governance-only | protect / next |
| Work persistence / lease / governed dispatch | 0.93 | 0.48 | +0.003 U | Q2 | ready | proposal | protect |
| Oracle Gemini Web live shadow E2E | 0.85 | 0.30 | +0.005 U | Q2 | blocked by Oracle/user availability | shadow | remember, do not interrupt |
| Generic node external execution | 0.88 | 0.24 | +0.002 U | Q2 | architecture incomplete | proposal | protect, not activate |
| Autonomous external action | 0.90 | 0.05 | +0.000 U | Q2 | governance intentionally incomplete | proposal | defer |

The matrix expresses attention, not authorization. An item crossing into Q1 does not increase its capability level.

## Updated principles produced by the re-review

### 1. Attention is not authority

> A system may decide that work deserves immediate attention without deciding that it may execute the work.

### 2. Representable unfinished work is not durable unfinished work

> A Deferred IR is only a data shape until it is durably indexed and queryable.

This corrects the earlier implicit assumption that creating `DeferredWorkPacket` alone solved buried-thread recovery.

### 3. Selection, authorization, execution and learning are separate powers

```text
Priority / Work selection
  -> Governance authorization
  -> Executor
  -> Receipt / SideEffect Ledger
  -> Experience / cognition
```

No stage inherits the authority of the next stage.

### 4. Governance controls cannot be caller-supplied evidence

> The governed component may request a capability; only the governance authority may resolve the profile that determines permission.

This now applies to cognitive promotion as well as external actions.

### 5. Global reconciliation must include missing relationships, not only bad data

The most valuable findings in this review were not wrong nodes; they were **missing edges between correct modules**.

Future global reviews should therefore inspect both:

```text
Knowledge graph health
+
Architecture/authority edge health
```

Examples: Priority -> Governance, Promotion -> Registry, Deferred -> Persistence, Dispatch -> Authorization.

## Current stop condition

Do not expand into Home/IoT, Universal One, autonomous external actions, or additional provider scope during this review cycle.

The next work should come from the re-prioritized Q1/Q2 core closure items above.

Production remains untouched; PR #3 remains experimental/draft.
