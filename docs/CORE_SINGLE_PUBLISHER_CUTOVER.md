# #1682 Core single-publisher cutover — operator runbook (candidate)

Scope: governed operations, NOT proof of authorization, merge, deployment, or acceptance.

## Verified baseline, 2026-11-22

- Protected main SHA: 77138a48a2661cd4e46f15c605d1db010367bc1a.
- Legacy core/integration SHA: 8c49a4de94b2796b3b33bfa3abd94874a97bd3fa.
- Both branches have different blobs at .github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml; the legacy branch still has its own automatic core/integration push-triggered converge path.
- GitHub ruleset agentos (ID 21844290) currently matches only refs/heads/main, not core/integration.
- Main-only draft PR #2366 will NOT disable the old branch workflow merely by merging to main.
- Workflow disable/enable is repository-workflow scoped rather than a safe branch-only off-switch; disabling an existing workflow can also disable its main ref entry point. Re-enabling it while the legacy branch still has its old YAML can re-expose the legacy event source.

## Operator preflight: do not mutate production until verified

1. Inventory Oracle consumers and exact authorized Core deploy/rollback/recovery workflows. Confirm that a genuinely independent rescue and publish channel exists; maintain at least one known-good channel.
2. Identify the actual GitHub Workflow ID/path and its enabled state through GitHub Actions administration; capture timestamped, sanitized readback.
3. Inventory in-progress or queued jobs with potential external side effects. Do not assume cancelling them rolls back a partially executed deploy.
4. Define exact-source and SQLite/WAL-consistent rollback acceptance before any control-plane rollout.

## Safe transition (requires GitHub operator/admin authority)

1. Apply a write-restriction or branch ruleset specifically to core/integration, without triggering a push; read back rule matching and actual actor/app bypass status. This blocks pushes but does NOT eliminate workflow_dispatch on the old branch.
2. Disable the legacy Core bundle workflow through the GitHub provider's workflow administration control; read back its actual disabled state. Preserve the independent rescue path, as the disable may affect the same path on main.
3. Ensure no active legacy deploy job can still update Oracle. Independently read Oracle's loaded PID/cwd/commit and service status.
4. Keep the old workflow disabled while promoting a distinct, governed, main-only workflow identity/path (or remove the old branch's definition using a separately authorized quarantined process). Do NOT re-enable the same workflow while its legacy definition still triggers core/integration.
5. Require protected-main PR human approval, explicit manual dispatch, 40-hex exact-main SHA fence and explicit broad-deploy acknowledgement; validate from GitHub provider event and source SHA, not just YAML content.
6. Attest immutable live Oracle worktree/systemd, WAL-consistent SQLite backup-and-restore, old-client lease_epoch transition, external side-effect fencing, and real end-to-end ONE recovery receipts before declaring #1682 closed.

## No-go conditions

- Passing PR CI, changing main YAML, or restricting core/integration pushes ALONE never proves the old workflow disabled.
- Re-enabling the same old Workflow ID while core/integration still holds a deploy-capable YAML is unsafe.
- No production task reroute to unverified Executor; eight orphaned tasks require restricted IR/owner provenance first.
- Do not merge into core/integration merely to remove its trigger while the original push trigger can fire.

## Tooling boundary

The present GitHub connection exposes read-only ruleset data but neither Workflow-disable nor ruleset-write actions. Administrative provider action and readback by an authorized operator is still required. Do not claim disabled state until verified.
