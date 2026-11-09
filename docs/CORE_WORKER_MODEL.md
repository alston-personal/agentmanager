# AgentOS Core Worker Model

Status: accepted canonical control-plane model from Issue #137. Current topology is published in `governance/core-workers.v1.json`; legacy `governance/core-workers.json` is a deprecated compatibility pointer.

## Purpose

The canonical AgentOS Core thread is architecture and authority control plane. It is not a global single-threaded executor for every Core issue or product dependency.

Core-owned work may execute in independent worker threads, agents or Nodes. A product/project blocks only the exact step whose declared dependency is unsatisfied. Unrelated work remains runnable.

## Authority split

Canonical Core owns architecture/invariants, Project Identity rules, triage/dependency semantics, acceptance criteria, integration decisions and deployment/publication authority.

A worker owns only its declared execution scope. It may branch, implement, test, collect evidence and report acceptance readiness. It does not gain protected-main publication, deployment-generation or unrelated-issue authority.

Privileged boundary or cross-Core architecture findings return to canonical Core for explicit decision/splitting rather than silently widening the reporting worker.

## Worker registry v1

The original `agentos.core-workers/v0` duplicated mutable issue/runtime status. It became contradictory: it still reported #117 `blocked` and hard-coded historical generation 6 after #117 had completed and runtime identity had moved to exact receipt-bound generations.

`agentos.core-workers/v1` therefore separates **topology** from **mutable status authority**:

- registry owns lane identity, scoped dependencies, blocking scope and explicit non-authorities;
- GitHub Issue state plus preserved acceptance evidence owns current worker completion;
- exact deployment/convergence/health receipts own live runtime identity;
- registry snapshots may summarize but never override newer issue/evidence state.

This avoids creating a second stale issue tracker inside the repository.

## Dependency semantics

Dependencies are directed, scoped edges, not project-wide pauses.

A dependency is satisfiable only when the required capability/evidence reaches the declared acceptance condition. Green CI, mergeability, generic `continue`, branch presence or source merge alone are insufficient for a live acceptance dependency.

Once accepted/completed evidence resolves a dependency, stale edges must be removed or explicitly retriaged. Historical provenance may remain without remaining an active blocker.

Example of the rule in practice: #117 is completed as of 2026-09-11 with bounded Oracle Codex Experience evidence. Older topology that says #160 blocks #117 is therefore stale. #160 may still contain independently useful provider-boundary work, but it requires separate triage and cannot remain an active #117 dependency merely because its original issue body says so.

## Parallel integration and exact rollouts

Workers may merge independently to `core/integration`. A concurrent accepted merge advancing integration is normal and must not invalidate an already-authorized exact-generation rollout.

Runtime authorization therefore uses:

1. snapshot the allowlisted governed integration ref;
2. fetch the requested immutable exact commit independently;
3. prove that exact commit is a member/ancestor of the snapped governed lane;
4. materialize/install only the exact commit;
5. verify fixed profile/health and persist a bounded receipt.

Stale workers refresh/transplant rather than force-merge over newer integration.

## Branch and environment semantics

Core development:

`core/issue-* -> core/integration -> explicit publication authority -> protected main`

Product development follows the same authority principle without requiring identical branch topology:

- feature/fix branches are mutable candidates;
- optional develop/integration may back POC/staging;
- `main` is accepted/promotion state, not an agent workspace;
- production resolves to exact accepted SHA/tag/artifact;
- POC/staging may resolve to exact candidate SHA/artifact;
- branch name alone never defines online authority.

Deployment receipts should identify project, repository, environment, source ref, exact SHA/artifact digest, timestamp/generation and terminal health/result.

## Current interpretation

Do not copy a static queue from this document. Read issue/evidence state and the v1 topology registry.

Important current decisions at this refresh:

- #117 Experience worker: completed with scoped Master Experience Floor evidence; no longer blocked.
- #238 product Employee acceptance: still open; recent source decisions bound missing wake receipts to `unknown`, gate product child launch on exact S4 `awaiting_claim`, and preserve privilege ordering in Worker Host startup. Live product VERIFIED markers remain separate.
- #152 Node↔executor lifecycle separation remains active architecture work.
- #290 Discussion Index remains candidate/draft, not canonical authority.
- #291 runtime checkout diagnosis/recovery remains bounded and fail-closed; unknown dirty state never authorizes generic reset/stash/recovery.
- #118 repository-boundary migration remains independent from product feature development.

## Invariants

1. Core ownership does not imply execution serialization.
2. Worker completion does not imply publication authority.
3. Products/projects block only dependency-scoped steps.
4. `main` is publication/accepted state, not active agent workspace.
5. Online state is environment + exact source/artifact + receipt, not branch name.
6. GitHub issue/evidence state outranks stale registry snapshots.
7. Live runtime identity is receipt-bound, not hard-coded in worker state.
8. Architecture findings return to canonical Core; worker scope does not silently expand.
9. Resolved dependencies are removed/retriaged rather than preserved forever as blockers.
