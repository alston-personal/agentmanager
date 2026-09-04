# AgentOS Core Branch / Runtime Authority Map

**Status snapshot:** 2026-09-04

This file describes branch authority, not live runtime state. Runtime identity must come from exact deployment/convergence receipts.

## Canonical roles

| Role | Ref / source | State | Authority |
| --- | --- | --- | --- |
| Core integration | `core/integration` | canonical / active | only long-lived Core engineering integration line; observed head at this refresh: `0c47fe2a0c325898814f4bea7c1e009359983477` |
| Issue work | `core/issue-<N>-<slug>` (or focused Core worker branch) | mutable candidate | bounded issue execution only; no publication authority |
| Documentation refresh | focused branch → PR to `core/integration` | mutable candidate | docs/evidence only unless change set explicitly contains governed implementation |
| Publication | `main` | protected accepted/publication history | publication/release state only; not an active agent workspace and not the source for normal Core runtime convergence |
| Live Core runtime | exact accepted `core/integration` SHA + runtime/worktree/service profile | dynamic | established only by deployment/convergence/health receipts, never by branch name alone |
| Historical feature/proposal branches | `feature/*`, old `fix/*`, legacy direct-to-main PR heads | frozen/migration provenance unless explicitly re-extracted | no new canonical Core development; still-needed deltas must be transplanted onto current issue branches |

## Development flow

```text
current core/integration
        ↓
focused core/issue-* worker
        ↓ tests + evidence + acceptance
        ↓ PR
core/integration
        ↓ separate explicit publication authority when required
protected main
```

A generic `continue`, green CI, mergeability, worker completion, capability availability, or live runtime success does not authorize publication to `main`.

## Runtime flow

Current Core runtime convergence is intentionally distinct from Git branch publication:

```text
accepted core/integration exact SHA
        ↓ bounded node.runtime.converge
fixed source-owned install/reconcile sequence
        ↓ health + capability/profile verification
sanitized convergence receipt
        ↓
live accepted runtime generation/profile
```

`node.runtime.converge` does not accept arbitrary executable/module/argv/shell/path/service/environment authority. Same-SHA requests still reconcile the fixed operating profile because source equality is not service/profile equality.

The historical statement `live generation 6 / f842bee...` is retired as current truth. It remains historical evidence only.

## Parallel worker model

The canonical Core thread is architecture/authority control-plane, not a global serial executor. Independent issues may run in parallel and integrate independently.

Dependencies are scoped edges. A product or Core project blocks only the exact step requiring an unresolved dependency. A separate worker advancing `core/integration` is normal; stale worker branches must refresh/transplant rather than force-merge over newer accepted work.

See `docs/CORE_WORKER_MODEL.md` and `governance/core-workers.json` for machine-readable worker/dependency state.

## Legacy proposal rule

Old direct-to-`main` or pre-`core/integration` proposals are not merge candidates wholesale. The canonical process is:

1. compare against current `core/integration`;
2. classify each delta as integrated / superseded / still-needed / product-owned / research-only;
3. preserve provenance/evidence;
4. transplant still-needed Core deltas onto a focused current branch;
5. run current guards/live acceptance as required;
6. integrate to `core/integration`;
7. close the historical PR as extracted/superseded.

This rule applies to the legacy proposal inventory tracked by #147 and prevents stale architecture from re-entering Core through historical branch ancestry.

## Product repository boundary

A product may use a Core runtime/deployment capability without moving product code into `agentmanager`.

- product implementation, tests, release intent and product-specific deploy semantics belong to the canonical product repository;
- Core owns generic bounded execution/deployment capability contracts, authority, receipts and cross-repository governance;
- POC/staging can consume an exact candidate SHA/artifact;
- production consumes an exact accepted/promoted source/artifact;
- environment + repo + source ref + exact SHA/artifact + receipt define online identity, not branch name by itself.

See `docs/PROJECT_REPO_MAP.md` and `governance/product-migrations.json`.

## Deprecated branch/runtime assumptions

Do not use these as current authority:

- `main` as the default Core development/runtime-convergence ref;
- direct agent development on protected `main`;
- long-lived legacy feature branches as integration lines;
- merging old proposal PRs wholesale because they are mergeable;
- fixed historical runtime generation numbers in docs as current live state;
- assuming repository HEAD equality means services/capabilities are converged;
- GitHub Actions as a steady-state fallback when ONE control-plane transport fails.

## Current active architecture areas

The branch map intentionally does not maintain a single "active issue" row. Core is multi-worker. Current architecture activity includes, among others:

- #117 Experience / Master Experience Floor;
- #152 Node↔executor separation and lifecycle inventory;
- #184 read-only Realm/Node/executor visual topology;
- #194 bounded executor jobs through ONE;
- #200 persistent Supervisor/Reconciler;
- #238 persistent product Employee operating acceptance;
- repository/product-boundary migration workers.

Issue status is read from GitHub / machine-readable worker state, not copied here as a manually synchronized queue.
