# Systemic Engineering First — high-risk change admission

Status: proposed, pending independent protected-branch review
Date: 2026-11-22
Owner: AgentOS engineering governance
Scope: architecture-sensitive and privileged AgentOS changes

## Decision

**Understand and inventory the system before changing it.** A high-risk
engineering request must move through **inventory → architecture/authority
model → adversarial risk review → integrated plan → bounded implementation →
live acceptance**. A request to "continue" does not skip the current phase.

Before code changes, recover the active ONE/IR context, source/runtime versions,
existing capability owner, historical incident, publisher and mutation ingress
inventory, authority / dataflow map, rollback boundary, and outstanding unknowns.
Separate source existence, CI, installed runtime readback and adversarial
acceptance. Mark what is verified vs inferred vs still unknown.

A newly discovered issue is a signal to reassess inventory coverage and the
system model, not automatic authorization for another local patch.

## Admission policy

- **Standard / reversible:** narrow change with bounded known impact; lightweight
  rationale, tests and rollback are sufficient.
- **High risk:** Core/runtime/Executor, action ingress, release/identity,
  governance or GitHub workflow changes. A PR-local
  `docs/governance/change-preflights/<change-id>.json` must record goal,
  inventory, reuse candidates, authority map, failure modes, plan, verification,
  rollback, unknowns and reviewers before implementation proceeds.
- The record must be **changed in the same PR**; old unrelated manifests are
  never transferable proof.
- For actual core/privileged implementation, the machine-readable record must
  state reviewed implementation readiness. This field is not trustworthy
  authorization by itself; actual protected-branch approval and runtime
  authorization are independently required.
- New unknowns affecting authority, data ownership, failure or rollback suspend
  the relevant implementation stage until the overall model is reconciled.
- Emergency mitigation can be proposed with a documented incident, bounded
  reversible change and explicit authorized operator review. No automatic
  bypass of production or branch authority.

## Acceptance evidence

1. PR-local change preflight record and scoped evidence references.
2. Independent human architecture/security/reliability review on high-risk PR.
3. CI negative tests for skipped inventories / forged reused plans.
4. For production changes, **separate** Oracle/ONE privileged mutation and
   version readback, concurrency/old-Executor negative tests, and tested rollback.
5. An explicit open-issues ledger; no claims of total closure from passing CI.

The CI guard checks *record presence and shape*, not truthfulness or runtime
authority. The owner cannot self-declare a production approval via a JSON file.

## Relation to existing governance

Reuses `AGENTS.md`, `docs/CURRENT_STATE.md`,
`docs/governance/decisions/GOV-2026-09-17-001-discovery-cost-reuse-floor.md`,
existing protected-branch authority and documentation-reality guards.
Does not create a second ONE, release epoch authority, engineering state store,
or parallel scheduler. For #1682, pause further ad hoc production release fixes
until the inventory and unified deployment authority plan are reviewed.

## Implementation status

This PR proposes the policy and an executable CI evidence-admission guard;
it does **not** establish cross-Executor runtime enforcement. The proposed rule
is in force in CI only after this PR is approved and merged under existing branch
authority. Wider rollout to other repositories and Executor runtimes requires
separate per-surface adoption receipts.
