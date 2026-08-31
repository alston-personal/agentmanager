# AgentOS Core Worker Model

Status: canonical proposal for Issue #137

## Purpose

The canonical AgentOS Core thread is the architecture and authority control plane. It is not a global single-threaded executor for every Core issue or every product dependency.

Core-owned work may execute in independent worker threads, agents, or nodes. A product project blocks only the exact step whose declared dependency is unsatisfied. Unrelated project work remains runnable.

## Authority split

The canonical Core authority owns:
- architecture and invariants;
- project/repository identity rules;
- issue triage and dependency graph;
- acceptance criteria and evidence requirements;
- integration decisions;
- deployment/publication authority.

A Core worker owns only its declared issue execution scope. A worker may branch, implement, test, collect evidence, and report `acceptance_ready`. It does not gain protected-main merge authority, deployment-generation authority, or authority over unrelated issues.

## Worker state contract

Canonical machine-readable worker state is recorded in `governance/core-workers.json` with schema `agentos.core-workers/v0`.

Allowed worker states:
- `queued`
- `running`
- `blocked`
- `acceptance_ready`
- `accepted`
- `failed`

Each worker records issue id, branch where known, dependencies, evidence refs, blocking scope, and explicit non-authorities.

## Dependency semantics

Dependencies are directed edges, not project-wide pauses.

Example:

`vendor-reputation:semantic-classification -> agentos-core#72`

Only `semantic-classification` waits for #72. Collection, UI, tests, documentation, or unrelated Vendor work continue unless they declare their own dependency.

A dependency is satisfiable only when its Core worker reaches `accepted` with the required evidence. `acceptance_ready`, CI green, PR mergeability, or a generic `continue` is not sufficient.

## Branch and environment semantics

Core development:

`core/issue-* -> core/integration -> explicit promotion PR -> protected main`

Product development should follow the same authority principle without requiring every repository to have an identical branch topology:

- feature/fix branches are mutable development candidates;
- an optional `develop`/integration branch may back POC or staging;
- `main` is accepted/promotion state, not an agent workspace;
- production deploys must resolve to an exact accepted SHA/tag/artifact;
- POC/staging may resolve to an exact candidate SHA from a feature/develop lane;
- no environment is authoritative merely because it tracks a branch name.

Every deployment receipt should identify project id, repository, environment, source ref, exact source SHA, artifact digest where applicable, and deployment timestamp/generation.

## Initial worker lanes

- #117 ONE Experience regression: separate worker; currently may depend on #72 and #130.
- #72 Antigravity/Claude executor liveness: shared executor-runtime worker.
- #130 Oracle self-hosted runner recovery: shared infrastructure worker.
- #105 governed GUI certification: independent worker.
- #96 LayoutLib development/deployment authority: independent worker.
- #66 governed Studio static release: independent worker.
- #118 repository-boundary cleanup: architecture/migration worker; must not globally block product feature work.

## Invariants

1. Core ownership does not imply execution serialization.
2. Worker completion does not imply publication authority.
3. Product projects block only dependency-scoped steps.
4. `main` is accepted/promotion state; active development does not write directly to it.
5. Online/staging/production state is identified by environment + exact source/artifact identity, never by branch name alone.
6. Machine-readable worker/dependency state is canonical enough for discovery, but acceptance still requires preserved evidence.
