# AgentOS Core Branch Model

Canonical branch roles:

- `main`: protected publication history only. It is not runtime/deployment authority.
- `core/integration`: the single long-lived Core development integration branch.
- `core/issue-<N>-<slug>`: short-lived Core issue branches, created from the accepted Core integration commit and merged back only after acceptance.
- Runtime/deployment authority is always an exact accepted commit SHA plus deployment generation; never a branch name.

Rules:

1. Do not create another long-lived Core feature branch.
2. Generic `continue` is not merge authority for `main`.
3. Issue branches must not contain temporary patch/carrier workflows in their final accepted diff.
4. Completed issue branches are retired after evidence is canonicalized and the accepted delta is integrated.
5. Publication to `main` is a separate release PR from `core/integration` and requires explicit human merge authorization.
6. `feature/realm-node-fabric-readiness` is legacy integration history and must not receive new Core work.

Transition state:

- `core/integration` starts from accepted live Core generation 6 commit `f842bee2cf7c24fc3bf7424bd121994562e829cd`.
- #105 work is canonical only on `core/issue-105-gui-control`.
- Superseded #105 aliases may temporarily remain as refs, but must not receive new commits.
