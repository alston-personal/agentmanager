# #1682 Core single-publisher cutover — operator runbook (candidate)

Scope: governed operations, NOT proof of authorization, merge, deployment, or acceptance.

## Verified baseline, 2026-11-22

- Protected main SHA: 77138a48a2661cd4e46f15c605d1db010367bc1a.
- Legacy core/integration SHA: 8c49a4de94b2796b3b33bfa3abd94874a97bd3fa.
- Both branches have different blobs at .github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml; the legacy branch still has its own automatic core/integration push-triggered converge path.
- GitHub ruleset agentos (ID 21844290) currently matches only refs/heads/main, not core/integration.
- Main-only draft PR #2366 will NOT disable the old branch workflow merely by merging to main.
- A SECOND distinct workflow, .github/workflows/oracle-action-runtime-rollout.yml on main, declares push-to-core/integration and a workflow_dispatch. Its `rollout` job requires core/integration, then calls the existing agentos.runtime repair dispatch through Runner Window. This is a separate Action Runtime publication route; do not mistake a Core bundle-only fix for full single publisher proof.
- A THIRD distinct legacy-branch workflow, .github/workflows/main-agent-model-routing-acceptance.yml, also has a core/integration push trigger and workflow_dispatch. Its accept job first calls agentos.runtime repair with GITHUB_SHA, and then runs executor job submission/inspection for model acceptance. It is not observational-only. This is a confirmed example, NOT an exhaustive inventory of all legacy workflows.
- Additional **confirmed legacy-branch direct or delegated mutation lanes**: core-integration-runtime-self-converge-20261007.yml (Push and manual runtime repair), dispatch-runtime-repair-20261012.yml (Push invokes reusable agentos.runtime repair), main-agent-relay-recovery-acceptance.yml (Push and manual relay restart), deploy-realm-fabric-core.yml (Push and manual Realm Fabric deployment), oracle-bootstrap-scheduler-rollout.yml (Push and manual installation), oracle-monitor-runtime-rollout.yml (Push and manual Monitor Runtime installation), and oracle-social-runtime-rollout.yml (Push-triggered social.runtime deploy). These are specific checked sources, NOT an exhaustive list of 453 YAML workflows in the legacy branch.
- An additional **separate publication path on main** is deploy-agentos-core.yml: manual workflow_dispatch accepts deploy_ref as a branch/tag/SHA, and permits empty expected_sha except for the special runtime-converger bootstrap mode. This means the main-only constraint of #2366 is NOT an effective global guard for other deploy workflows. Its explicit recovery/bootstrap purpose needs an owner-approved redesign rather than silent forced disable.
- The 2026-11-22 legacy Git Tree contained **453 workflow YAML paths without truncation**. Some are historical/diagnostic; do not label all 453 as active publishers without source trigger/job inspection.
- Existing .github/workflows/oracle-core-runtime-converge-now.yml is NOT a general recovery deploy: it only restarts os-chronos and agentos-core-supervisor from the current immutable Core release, without choosing/restoring another source or restoring Control Plane SQLite.

- Workflow disable/enable is repository-workflow scoped rather than a safe branch-only off-switch; disabling an existing workflow can also disable its main ref entry point. Re-enabling it while the legacy branch still has its old YAML can re-expose the legacy event source.

## Operator preflight: do not mutate production until verified

1. Inventory Oracle consumers and exact authorized Core/Action Runtime deploy/rollback/recovery workflows, including oracle-action-runtime-rollout.yml, main-agent-model-routing-acceptance.yml and any other core/integration-pinned push/dispatch route. Do not treat oracle-core-runtime-converge-now.yml as a source/DB recovery channel. Confirm a genuinely independent rescue and publish channel exists before removing any working entrypoint.
2. Identify the actual GitHub Workflow ID/path and its enabled state through GitHub Actions administration; capture timestamped, sanitized readback.
3. Inventory in-progress or queued jobs with potential external side effects. Do not assume cancelling them rolls back a partially executed deploy.
4. Define exact-source and SQLite/WAL-consistent rollback acceptance before any control-plane rollout.

## Safe transition (requires GitHub operator/admin authority)

1. Apply a write-restriction or branch ruleset specifically to core/integration, without triggering a push; read back rule matching and actual actor/app bypass status. This blocks pushes but does NOT eliminate workflow_dispatch on the old branch.
2. Disable/quarantine the identified legacy publishing workflow identities—including the Core bundle and any independently confirmed legacy Action Runtime rollout—through approved GitHub provider administration controls, and read back each disabled state. Preserve an independently proven rescue channel: a workflow-disable can affect the same path on main.
3. Ensure no active legacy deploy job can still update Oracle. Independently read Oracle's loaded PID/cwd/commit and service status.
4. Keep the old workflow disabled while promoting a distinct, governed, main-only workflow identity/path (or remove the old branch's definition using a separately authorized quarantined process). Do NOT re-enable the same workflow while its legacy definition still triggers core/integration.
5. Require protected-main PR human approval, explicit manual dispatch, 40-hex exact-main SHA fence and explicit broad-deploy acknowledgement; validate from GitHub provider event and source SHA, not just YAML content.
6. Attest immutable live Oracle worktree/systemd, WAL-consistent SQLite backup-and-restore, old-client lease_epoch transition, external side-effect fencing, and real end-to-end ONE recovery receipts before declaring #1682 closed.

## No-go conditions

- Passing PR CI, changing main YAML, or restricting core/integration pushes ALONE never proves the old workflow disabled.
- Stopping only the Core bundle Workflow is not enough if independent core/integration Runtime, Realm Fabric, Relay, Scheduler, Monitor or Social deployers remain callable; inventory and quarantine must cover every proven publisher before acceptance.
- A single-publisher claim must also fence *other main-hosted workflows* with arbitrary deploy_ref and optional expected_sha; source restrictions in #2366 apply only to that PR's target workflow.
- Re-enabling the same old Workflow ID while core/integration still holds a deploy-capable YAML is unsafe.
- No production task reroute to unverified Executor; eight orphaned tasks require restricted IR/owner provenance first.
- Do not merge into core/integration merely to remove its trigger while the original push trigger can fire.

## Tooling boundary

The present GitHub connection exposes read-only ruleset data but neither Workflow-disable nor ruleset-write actions. Administrative provider action and readback by an authorized operator is still required. Do not claim disabled state until verified.


## 2026-11-22 complete read-only census (scope and coverage)

Source snapshots are pinned to `core/integration@8c49a4de94b2796b3b33bfa3abd94874a97bd3fa` and `main@77138a48a2661cd4e46f15c605d1db010367bc1a`; see [GitHub Actions run 44969309463](https://github.com/alston-personal/agentmanager/actions/runs/44969309463). The source audit script scans every YAML and local reusable Workflow without executing legacy jobs. Detailed machine-readable inventories are attached as the run artifact.

- Old: **453** YAML total = **449 executable-root paths** plus **4 nested `history/` reference files**. Of the 449 root workflows, **254** declare a `core/integration` push trigger. **122** of these were flagged for a static side-effect signal. Importantly, **66 of the 122** are flagged only because they use a remote Shell; such a signal alone does **not** prove mutation.
- Main: **617** YAML total = **613 root paths** plus **4 nested history files**; **248** root workflows still describe a `core/integration` push trigger in their source. Those exact source triggers must be assessed at the legacy branch, not dismissed because they appear on main.
- Cross-ref: every one of the old **449** root workflow paths also exists in main. **400** source-identical and **49** source-different; main has **164** root-only paths. Of the old 122 push+side-effect candidates, **10** differ on main and **112** retain identical source bytes across both branches.
- Existing baseline `.agentos/governance/legacy-direct-oracle-workflows.txt`: **150** paths, all still present. Only **3 of 122** old push+side-effect candidates appear in that baseline, leaving **119 outside it**. Eight baseline paths retain an old push trigger. Baseline inclusion is not provider disabled-state proof.

**Classification caution:** `mutating_signal` means a static regex or local-reusable-workflow propagation flag (SSH, service operation, deployment-like script, etc.), *not* confirmed deployment. `no_mutating_signal_observed` likewise does not certify safety. Further investigate direct calls, actual job preconditions, provider Workflow enabled state, branch protection/bypass identities, and Oracle-loaded SHA before any removal or acceptance. The audit is repeatable, read-only, with no GitHub provider/ONE/Oracle mutation.

**Operational implication:** the original 150-item quarantine list is not a complete authority registry. Do not assume that only three old publishers exist: the 122 flagged subset includes false positives, but 119 unlisted signals require owner review. Quarantine via provider-side admin controls and trusted main-only release authority must be designed system-wide, not file-by-file accidental fixes.
