# AgentOS Closure Recovery Wave 1

Status: active audit / execution checkpoint
Date: 2026-08-27

## Why this wave exists

The first Closure Ledger proved that AgentOS has a recurring pattern: architecture ideas, role contracts, skills, prototypes, and partial runtimes can survive in the repository while the final operating loop disappears or is never completed. This wave converts that inventory into an execution order.

## Priority rule

Prioritize gaps that unblock multiple other capabilities. Do not add another abstraction if an existing role, skill, resolver, or runtime can be recovered and completed instead.

## P0 — Agent Organization / Employee Runtime

Existing evidence already proves:

- Root / parent-role inheritance exists.
- Role contracts and role registry exist.
- Skills exist, including publishing/deployment skills.
- Governance Directory can resolve owners/providers.
- Project-scoped durable memory exists.

What is not yet closed:

- durable `AgentInstance` identity;
- employee-scoped memory namespace;
- assignment and activation lifecycle;
- agent-to-agent inbox/outbox or equivalent message transport;
- handoff / completion receipts at employee scope;
- executor binding that can change model/provider without changing employee identity.

### Minimal acceptance loop

Do not attempt a full multi-agent company first. Prove one employee:

`assignment -> resolve employee -> hydrate inherited role + skills + employee state -> execute/handoff -> receipt -> assignment state update`

Use `governance.spec_steward` as the first reference employee because the role already exists and naturally owns closure-gap tracking.

## P0 — Closure Steward becomes operating

The Closure Ledger must not become another passive document. `governance.spec_steward` should eventually consume it, identify non-terminal items, create/refresh assignments, and emit receipts showing what moved, remained blocked, or was explicitly deferred.

Until that runtime exists, closure management is still human/LLM-triggered rather than continuously operating.

## P1 — Cognitive Thread / HEAD / Return Stack

Treat this as working-assignment state inside the Employee Runtime, not as a parallel organization system.

Required later evidence:

- nested topic diversion preserves parent HEAD;
- explicit return restores the parent assignment position;
- stale events cannot roll back a newer thread HEAD;
- cross-model hydration preserves the same active thread and return path.

## P1 — Chronicle / writing / publishing loop

Do not invent duplicate Writer/Publisher infrastructure before recovering existing capabilities.

Known pieces already exist:

- Chronicler role contract is proposed;
- Matters Publisher skill is implemented;
- Zeus-writer has real three-projection content that needs chronicle synchronization.

After the employee kernel exists, use Zeus-writer as the first multi-role collaboration case:

`Chronicler -> Weaver/Writer responsibility -> Claw review -> publisher skill -> human authorization for public release`

## P1 — Capability learning loop

Keep LayoutLib as the first reference domain, but require the same Closure Ledger gates. The target is still one end-to-end receipt-backed loop from execution evidence through governed canonical learning and fresh-node reuse.

## Repository-native governance gap

After Closure Audit PR #16 was merged, `main` advanced to commit `ba31e3625f57b5b8bfb0ea1f506ed90beaad7555`. GitHub still reports `main` as `protected: false` with no required status checks.

This does not prove the later commit was unauthorized, but it proves AgentOS policy is not backed by an independent repository-native enforcement layer. `protected-branch-authority` therefore remains `GUARDED`, not `CLOSED`.

## Completion discipline for this wave

A work item may move forward only with evidence for the new stage. No item becomes `OPERATING`, `GUARDED`, or `CLOSED` because a design document says it should.

This wave should stop and ask for human authorization before any merge to `main`.
