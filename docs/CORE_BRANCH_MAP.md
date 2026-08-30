# AgentOS Core Branch Map

Status snapshot: 2026-08-30

| Role | Ref | State | Authority |
| --- | --- | --- | --- |
| Publication | `main` | protected / active | repository publication only; current observed head `0add7f8703980db055a4680807990ac1b92aafa1` |
| Core integration | `core/integration` | canonical / active | only long-lived Core development integration line |
| Live Core runtime | generation 6 / `f842bee2cf7c24fc3bf7424bd121994562e829cd` | converged / released | deployment authority; branch-independent |
| Active Core issue | `core/issue-105-gui-control` | active | canonical #105 work; clean one-commit delta from live gen6 base |
| Legacy integration | `feature/realm-node-fabric-readiness` | frozen / legacy | historical evidence only; observed head `9e0c7c035f7c01c125a5ab7f8cc5de4db7cba437`; no new Core work |
| Retired alias | `fix/issue-105-core-gui` | superseded | ref collapsed to canonical #105 commit; do not use |
| Retired alias | `fix/issue-105-governed-gui-control` | superseded | ref collapsed to canonical #105 commit; do not use |

## Flow

`core/integration` → `core/issue-<N>-<slug>` → acceptance/evidence → integrate back to `core/integration`.

Publication is a separate, explicit release operation: `core/integration` → PR → protected `main`.

Deployment authority is never inferred from either branch. Always record and verify `deployment_generation + exact accepted commit SHA`.

## #105 current canonical state

- Base: live Core generation 6 commit `f842bee2cf7c24fc3bf7424bd121994562e829cd`.
- Canonical issue branch: `core/issue-105-gui-control`.
- Canonical issue commit: `62e884c15cc4ad18f6564ddcb33aa94d91ca5c20`.
- Final diff contains only Controller GUI governance, Control Inbox compact/redacted artifacts, regression tests, Node GUI acceptance evidence, and the branch-model document.
- Temporary patch workflow/helper are not present in the canonical issue branch.
