# AgentOS Core Branch Model

Canonical branch roles:

- `main`: protected publication history only. It is not runtime/deployment authority.
- `core/integration`: the single long-lived Core development integration branch.
- `core/issue-<N>-<slug>`: short-lived Core issue branches, created from the accepted Core integration commit and merged back only after acceptance.
- Runtime/deployment authority is always an exact accepted commit SHA plus deployment generation; never a branch name.

Rules:

1. Do not use multiple long-lived Core feature branches.
2. Do not merge generic `continue` work to `main`.
3. Issue branches must not contain temporary patch/carrier workflows in their final accepted diff.
4. Completed issue branches are deleted after their evidence is canonicalized and their change is integrated.
5. Publication to `main` is a separate release PR from `core/integration` and requires explicit human merge authorization.

Transition cleanup:

- `feature/realm-node-fabric-readiness` is legacy integration history. Do not add new Core work to it; migrate accepted deltas/evidence into `core/integration`, then retire it.
- For #105, consolidate the accepted Node GUI evidence and Core GUI-control delta into one `core/issue-105-gui-control` line before live certification.
- Branches created accidentally or superseded during #105 (`fix/issue-105-core-gui`, `fix/issue-105-governed-gui-control`) are transitional only and must be retired after consolidation.
