# AgentOS Core Worker Model

Status: accepted canonical control-plane model from Issue #137; machine state is continuously reconciled in `governance/core-workers.json`.

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

When a worker discovers a privileged boundary, new cross-Core protocol, or architecture/invariant change, it reports that decision point back to canonical Core. Canonical Core may accept a bounded decision, reject it, or split it into a new dependency worker rather than allowing scope creep inside the reporting issue.

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

The prose issue body is historical intent; the machine graph is the current dependency projection. The graph must be reconciled when evidence resolves a dependency. A closed/completed issue is not automatically `accepted` without evidence, but once canonical acceptance evidence exists it must not remain as a stale blocker.

## Dependency semantics

Dependencies are directed edges, not project-wide pauses.

Example:

`vendor-reputation:semantic-classification -> agentos-core#72`

Only `semantic-classification` waits for #72. Collection, UI, tests, documentation, or unrelated Vendor work continue unless they declare their own dependency.

A dependency is satisfiable only when its Core worker reaches `accepted` with the required evidence. `acceptance_ready`, CI green, PR mergeability, or a generic `continue` is not sufficient.

Resolved infrastructure dependencies and unretired product carriers are separate states. A product carrier may remain open for migration/parity after the shared Core capability it once depended on has been accepted.

## Architecture-return pattern

A worker architecture report does not authorize that worker to widen privileged contracts itself.

Current accepted examples:

- #117 discovered the ubuntu-owned Codex identity/executable boundary. Canonical Core split the privileged provider work into #160 and chose an isolated fixed-provider Codex relay/service/root rather than generic executable selection.
- #117 also distinguished passive Experience hydration from a fully ONE-aware executor. Canonical Core kept passive hydration inside #117 acceptance and split the higher bidirectional handshake into #161, which does not block #117.
- #72 received bounded authority for sanitized Claude liveness diagnostics only; this did not grant generic shell/argv, credential access, permission broadening, or timeout-policy changes.

This pattern keeps execution parallel while preserving one architecture authority plane.

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

## Current worker-lane interpretation

Do not copy a static dependency list from this document into a worker. Read `governance/core-workers.json`.

As of the 2026-08-31 reconciliation:

- #117 ONE Experience regression is a separate worker and is blocked only on #72 (Claude liveness) and #160 (governed Codex relay). #130 is resolved; #161 is not a #117 blocker.
- #72 Antigravity/Claude executor liveness is a running shared executor-runtime worker with no Core dependency.
- #130 Oracle self-hosted runner recovery is accepted and no longer appears in dependency edges.
- #105 governed GUI certification remains a running independent worker pending its live certification evidence.
- #96 LayoutLib authority has its generic policy accepted in `core/integration`; only live exact-candidate POC receipt/public acceptance remains.
- #66 governed Studio static release is accepted; ArcanaForge's remaining source/artifact provenance is a product migration gate, not a #66 Core dependency.
- #118 repository-boundary cleanup remains a running architecture/migration worker and must not globally block product feature work.
- #137 worker/dependency control-plane is accepted.
- #147 legacy proposal delta extraction remains an independent architecture-extraction worker.
- #160 isolated fixed-provider Codex relay is a separate privileged-executor worker and blocks only #117's real Codex regression step.
- #161 ONE-aware executor handshake is a separate architecture worker and does not block passive Experience hydration.

## Invariants

1. Core ownership does not imply execution serialization.
2. Worker completion does not imply publication authority.
3. Product projects block only dependency-scoped steps.
4. `main` is accepted/promotion state; active development does not write directly to it.
5. Online/staging/production state is identified by environment + exact source/artifact identity, never by branch name alone.
6. Machine-readable worker/dependency state is canonical enough for discovery, but acceptance still requires preserved evidence.
7. Architecture findings return to canonical Core; reporting workers do not silently acquire cross-Core or privileged authority.
8. Resolved dependencies are removed from active edges; historical provenance remains as evidence, not as a permanent blocker.
