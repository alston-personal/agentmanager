# AgentOS Core Branch / Runtime Authority Map

**Status snapshot:** 2026-09-11

This file describes branch and runtime authority boundaries. It does not claim a branch HEAD is the live runtime.

## Canonical roles

| Role | Ref / source | State | Authority |
| --- | --- | --- | --- |
| Core integration | `core/integration` | canonical / active | only long-lived Core engineering integration line; observed head at this refresh: `5093b59da5d45cdd016d606a7e2cb8abdb4cf22e` |
| Issue work | `core/issue-<N>-<slug>` or focused Core worker branch | mutable candidate | bounded issue execution only; no publication authority |
| Documentation refresh | focused branch -> PR to `core/integration` | mutable candidate | docs/evidence only unless change set explicitly includes governed implementation |
| Publication | `main` | protected accepted/publication history | publication/release state only; not normal Core development/runtime-convergence source |
| Live Core runtime | exact accepted integration commit + runtime/worktree/service profile | dynamic | established only by deployment/convergence/health receipts |
| Historical feature/proposal branches | `feature/*`, old `fix/*`, legacy direct-to-main heads | frozen/migration provenance unless re-extracted | no new canonical Core development |

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

`continue`, green CI, mergeability, worker completion, capability availability or live runtime success never authorizes publication to `main`.

## Exact-generation runtime flow

```text
accepted exact Core commit
        ↓
snapshot allowlisted core/integration ref
        ↓
fetch requested immutable commit separately
        ↓
prove exact commit is ancestor/member of snapped governed lane
        ↓
materialize only exact commit bytes
        ↓
fixed source-owned install/reconcile
        ↓
health + capability/profile verification
        ↓
sanitized receipt
```

This is intentionally not `requested_sha == current branch HEAD`. That older equality assumption created a race: another accepted worker could advance `core/integration` while a valid rollout was in progress. #320/#322 replaced it with immutable exact-commit + governed-lane ancestry proof.

Same-source requests may still reconcile the fixed operating profile because source equality is not service/profile equality.

## Parallel worker model

The canonical Core thread is architecture/authority control-plane, not a global serial executor. Independent issues may run and integrate concurrently.

That means advancing `core/integration` while another rollout/worker is active is expected. Stale worker branches refresh/transplant onto current integration rather than force-merging or widening deployment authority.

Dependency edges block exact steps, not entire products/projects.

## Current decision highlights

- #117 is **completed** as of 2026-09-11 for its bounded Oracle Codex Experience acceptance. Do not continue to list it as a blocked active worker.
- #238 remains open for real Zeus Writer / YouTube AI Manager persistent Employee production acceptance; recent source fixes harden wake timeout, S4 preclaim readiness and Worker Host privilege transition, but live product VERIFIED markers remain pending.
- #290 Discussion Index is still a draft candidate (#293), not canonical state/authority.
- #291 Oracle checkout/runtime diagnosis remains a bounded diagnostic/recovery concern; dirty checkout or rollout evidence must be read from the latest receipt rather than copied into this branch map as permanent truth.
- #152 continues Node↔executor lifecycle separation work.
- Product/repository migration remains governed by `docs/PROJECT_REPO_MAP.md` and `governance/product-migrations.json`.

## Legacy proposal rule

Old direct-to-`main` or pre-`core/integration` proposals are not wholesale merge candidates. Compare against current integration, preserve provenance, extract only still-needed accepted deltas onto focused current branches, rerun current guards/live acceptance, then close the historical carrier as extracted/superseded.

## Product repository boundary

A product may consume Core runtime/deployment capabilities without putting product code in `agentmanager`.

- product implementation/tests/release intent/product deploy semantics belong to canonical product repositories;
- Core owns generic bounded capability contracts, authority, receipts and cross-repository governance;
- POC/staging may use exact candidate SHA/artifact;
- production uses exact accepted/promoted source/artifact;
- environment + repo + source ref + exact SHA/artifact + receipt define online identity.

## Deprecated branch/runtime assumptions

Do not use as current authority:

- `main` as default Core development/runtime-convergence ref;
- direct agent development on protected `main`;
- fixed historical runtime generation numbers as current truth;
- repository HEAD equality as proof services/capabilities are converged;
- moving `core/integration` HEAD equality as exact-generation rollout authorization;
- long-lived legacy feature branches as integration lanes;
- wholesale legacy proposal merge because it is mergeable;
- GitHub Actions as steady-state fallback when ONE transport fails.

Issue state is read from GitHub/evidence, not manually duplicated here as a queue.
