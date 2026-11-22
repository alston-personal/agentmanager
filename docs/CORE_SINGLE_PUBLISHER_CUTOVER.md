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


## 2026-11-22 GitHub provider-level enabled-state readback

A second strictly read-only GitHub-hosted census (Actions run [44969701146](https://github.com/alston-personal/agentmanager/actions/runs/44969701146)) used scoped `actions:read` access to enumerate actual GitHub Workflow IDs, paths, and `state`, then joined them against the pinned source inventories without executing any legacy Workflow.

- GitHub Provider returns **1,076** distinct Workflow path identities, all with `state=active` in the fetched result.
- **449/449** legacy root Workflow paths correspond to an `active` provider identity. The **122** static old-push/possible-side-effect candidates are therefore **122/122 provider-active**. This is enabled-state evidence, NOT proof an individual branch/job can execute or that it has changed Oracle.
- Main currently contains **613** root source paths. **463** other provider-active paths appear in **neither** pinned `main` nor `core/integration` source snapshots. They may be historical identities or defined on other branches, and **cannot be automatically declared live publishers**. Nevertheless, they require provider lifecycle/branch-origin classification and eventual safe retirement; their registration state is not `disabled`.
- Keep three inventories distinct: **(a) source YAML event path**, **(b) provider workflow active/disabled state**, **(c) authenticated Runtime ingress permission and successful production mutation**. They are NOT interchangeable.

**Governance gap is broader than branch convergence:** preventing regressions requires a provider-level lifecycle registry for every Workflow ID, including previously removed-source identities, and a shared exact-main/Realm/release-generation fence at the trusted deployment ingress. Do not bulk-disable all 463 before owner/recovery inventory, and do not interpret all 1,076 as deployers. The audit did not change any workflow state.

## 2026-11-22 — Bounded recent Workflow-run evidence (candidate)

The Provider registry reports an active Workflow identity even when its source branch is no longer present. To prioritize operator review without implying a deployment, the existing **read-only** legacy workflow inventory now joins the 30-day GitHub Actions workflow-run history to each Provider Workflow ID and source classification. It records `head_branch`, `event`, observed count, success *as Actions conclusion only*, and last seen timestamps; it never fetches job logs, credentials, artifacts from the run, or causes execution.

Priority `p0` identifies an already flagged legacy push/side-effect candidate with an **observed core/integration Push run**; `p1` indicates another observed legacy-branch run; `p2` means no observed legacy run in the bounded sample; `p3` covers other registered workflows. An incomplete paginated scan is explicitly marked. `p2` is not disabled, `p0` is not proof of production changes, and a successful GitHub Actions run is not proof of a correct Oracle release. Actual recent-run totals and priority counts must come from the corresponding GitHub CI artifact, not static assertions.

This remains a triage aid. Global ownership attribution, provider ruleset write, Workflow disable, release ingress fencing and real rollback acceptance are still separate gates.

## 2026-11-22 — Root cause and permanent prevention architecture (governed proposal)

**Evidence of release-authority split from current main source**:

- `agent_core/runtime_converge_contract.py` currently sets `ALLOWED_SOURCE_REFS={"core/integration"}` for `node.runtime.converge`, and `agentos_node/bootstrap_control.py` constructs that `source_ref` for Oracle runtime converge. The code verifies a 40-hex `source_commit`, but the existing converge preflight checks only that the requested commit is an ancestor of the chosen branch head. Neither ancestry nor exact SHA proves a human-approved immutable **main release**.
- `agent_core/runtime_ota.py` separately accepts `main`, `core/integration`, and `feature/realm-node-fabric-readiness` in its desired-state `ALLOWED_SOURCE_REFS`. This is appropriate evidence of an earlier broader OTA compatibility contract, NOT a global production release authority.
- `agentos_node/bootstrap_control._run_canonical_script` retrieves executable script bytes from a caller-provided exact commit, or `origin/main` when omitted. Its request checks owner, action allowlist, TTL, and SHA shape, but a shared release-generation approval/fencing check is **not** enforced uniformly on every mutating action at this helper boundary.
- Repository governance for protected `main` checks PR/human approval and source-level direct-main mutation patterns. GitHub Workflow provider enabled state, ingress OIDC permissions, successful Actions runs, approved release identity and the actual installed Oracle PID are separate evidence planes.

### Preventive invariant

**Every production-changing operation must be authorized by the target Runtime against ONE durable release authority, not by the initiating Workflow or Executor.** A development Executor may build a candidate, but cannot publish merely by choosing a SHA, and CI success cannot issue deployment authority.

### Implementation contract and phased rollout (not yet implemented)

1. **Release identity at one existing authority**: add a governed release-intent record to the existing ONE/Realm release authority, not another writable registry. The record must bind repository, project/Realm, environment, exact approved `main` commit, immutable artifact digest, operation scope, approver and authorization reference, expiry, monotonic release epoch, and rollback parent. The logical approval is independent of the GitHub workflow filename or the user-supplied `source_ref`.
2. **Preflight at the true write boundary**: all production-changing existing carriers (Action Relay runtime converge, bootstrap script execution, Runner Window `agentos.runtime repair`, `social.runtime deploy`, Realm Fabric installers, direct SSH/systemd and provider deployment workflows) must call the *same verified authorization decision* immediately before the first external side effect. OIDC or another authenticated principal must be checked against authorized Realm, capability, Workflow identity and environment; user-supplied SHA or `session_id` is not identity proof.
3. **Source check beyond commit ancestry**: verify the exact commit resolves to the approved protected-main release and artifact digest; for rollback, authorize a narrowly scoped previous known-good release in a separate expiring rollback intent. Do not infer production permission from `git merge-base --is-ancestor` or from `source_ref=main` alone. Never allow a stale Workflow to select a new commit by mutable ref.
4. **Epoch fencing + CAS at target**: before changing worktrees/systemd/services/SQLite, claim a persisted `release_epoch` lease with compare-and-swap against the target's current generation. After staging and before publish, recheck the lease/epoch. Older and concurrent deploys are rejected (including a delayed Workflow job resumed from queue). Receipt must contain request ID, approval ID, candidate SHA/digest, expected and observed previous epoch, resulting epoch, loaded PID/cwd/version, and sanitized outcome. External filesystem and systemd writes require the same fencing; rejecting a stale database receipt alone is insufficient.
5. **Atomic publish and recovery**: retain immutable worktrees, take WAL-consistent SQLite backup, snapshot relevant systemd settings and capability markers, stage and health-check separately, atomically switch current selector only after approval. Verify newly running PID and health; on failure roll back *all* affected layers and emit an authoritative rollback receipt, never `git reset --hard` on an unknown dirty checkout.
6. **Two isolated communication lanes**: normal update lane and minimum rescue lane use separately versioned adapters and must not be upgraded together. A rescue operation is scoped to restoring an approved last-known-good generation and is not a universal branch/SHA bypass. When upgrading the rescue adapter, normal lane must be proven healthy first; after rescue validation, only then update normal lane. Include explicit failure-injection tests for both update orders.
7. **Provider hygiene as defense in depth**: permanently quarantine old-branch writers using GitHub admin Rulesets, workflow identity management and independent disabled-state readback. Reuse the existing quarantiner only after owner-by-owner review; do not run its branch-pushing codemod while the old push trigger can deploy. Ratchet the existing whole-tree scanner so newly introduced production-mutating workflow paths on any branch require an approved release-lane classification. Treat 463 historical provider identities as lifecycle candidates, not proof of 463 deployers.
8. **Migration without downtime**: first add *shadow read-only* release checks to existing carriers; verify all legitimate current publishers and rescue paths. Then enforce on one low-blast-radius operation, test old-client compatibility and fail-closed rollback, deploy a guarded target Runtime with exact Oracle readback, and only thereafter disable unguarded legacy issuers. Do not flip a global deny before a rescue path has been tested.

### Required negative tests before release acceptance

- A valid GitHub Actions OIDC identity and SHA from `core/integration` without an approved main release is **DENIED**.
- A `main` SHA without current approval/Realm/operator authorization is **DENIED**.
- A previously approved but stale epoch, a replayed dispatch, and simultaneous Executors attempting the same installation are **DENIED before any external mutation**.
- A malicious or stale Workflow that invokes `agentos.runtime repair` indirectly via a reusable Workflow is **DENIED at the target boundary**.
- A release that updates the live service but fails a SQLite/WAL or capability-marker verification automatically restores the prior approved generation; a Receipt proves full state restoration.
- Emergency rescue remains functional after a deliberately broken normal adapter, and the general update lane remains functional during a rescue-adapter failure; neither bypasses release scope.
- No declared success until hosted tests, authorized Oracle live PID/DB readback, operator approvals, and two consecutive real ONE execution receipts are all present.

**Current implementation status:** these are engineering requirements, not accepted code. The existing #2366 only fences its specific Core Bundle Workflow on protected main; #2365 only adds Dispatcher heartbeat and read-only diagnostics. Neither establishes a universal target-side release gate, and neither may be deployed based only on CI.

## 2026-11-22 — Release-authorization gate phase A implemented as pure evaluator

Candidate branch adds `agent_core/release_authorization.py` and `tests/test_release_authorization.py` to model a **fail-closed trusted release intent preflight**. Positive evaluation requires a separately authenticated governance record binding protected `main`, exact SHA, artifact digest, approval Receipt, release epoch, operation, repository, Realm, environment, authenticated principal and expiration. Target state must separately supply matching repository/Realm/environment and an older persisted release epoch. Unit tests deny legacy sources, other Realm, wrong capability, expired/unapproved intent, missing authority, caller-supplied self-approval, replay and stale epochs.

**Crucial integration boundary:** The new function **does not read trusted ONE records, acquire CAS leases, mutate releases or authorize production by itself**. Callers must never pass a copy of user request fields as `approved_intent` or `observed_target`. A matching pure decision is explicitly named `preflight_eligible_requires_atomic_target_cas`. It is not wired into `agentos_node/runtime_converge_action_relay.converge_runtime` or other live mutation paths pending a verified ONE/Realm-backed authority adapter, independently tested recovery lane, and target-side atomic fencing. It is **not production protection** yet; enabling an untrusted local substitute would create a security bypass.

The acceptance sequence is: confirm authoritative data contract / read-only adapter → test negative matrix → add target-side durable epoch CAS and just-before-cutover recheck → migrate one low-risk carrier under monitored rollout → emergency rollback test and Oracle readback → expand to all write-capable carriers → provider-admin quarantine of legacy issuer identities. Do not block existing rescue channels globally before these steps.

### PR metadata check / event-snapshot caution

The existing `AgentOS IP Provenance Guard` reads the PR body from its GitHub Actions event snapshot. Re-running a failed job from an older event does not necessarily refresh that original snapshot after PR metadata is edited. The PR now has the required standalone `IP-Scope: personal-independent` line; a **new PR commit event** is necessary to validate the corrected metadata with a fresh event. Never suppress the guard or silently interpret the stale re-run as a current policy failure.
