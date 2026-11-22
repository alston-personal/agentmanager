# #1682 Production Publisher & Authority Inventory — baseline v0

Status: INCOMPLETE / READ-ONLY SOURCE INVENTORY
Date: 2026-11-22 (Asia/Taipei)
Owner: AgentOS #1682, pending independent architecture/security/reliability review
Pinned baseline: `alston-personal/agentmanager main@77138a48a2661cd4e46f15c605d1db010367bc1a`

This is a pre-implementation inventory, **not** a rollout authorization, an exhaustive publisher census, or a verified Oracle runtime receipt. PR #2366 and #2367 are separate unmerged Draft candidates and their changes must not be presented as currently active main code.

## Goal and invariant

Before any further production release mutation, enumerate and reconcile all paths capable of changing runtime state, the approval authority that grants each operation, the exact executor identity, the mutable target, the CAS/fencing state and the independent rollback/rescue path. ONE must remain the canonical authorization/continuation authority; an individual Workflow or Executor must not independently grant production publication rights. Existing, verified safety mechanisms should be reused rather than duplicated.

## Known source-level paths and authority boundaries

| Source path (main) | Observed trigger/operation | Authority/generation status | Evidence level | Unresolved |
|---|---|---|---|---|
| `.github/workflows/deploy-agentos-core.yml` | `main` push and manual `workflow_dispatch` with `deploy_ref`; remote SSH; Git worktree, service installer, systemd, symlink | Contains a local rollback trap but still exposes a generalized deployment entry; not proven to use ONE release intent or shared cross-writer fencing | Source verified | Resolve manual ref validation, expected SHA, actor, target write permissions, rollback health |
| `.github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml` | `core/integration` push/manual paths; remote SSH, Git worktree and systemd changes | Direct external mutation path; main copy not yet changed to #2366 proposal | Source verified | Legacy branch workflow identity and trigger, provider-level disable/quarantine, all modified services |
| `.github/workflows/oracle-action-runtime-rollout.yml` | `core/integration` push/manual; runtime rollout | No shared, proven ONE approval + target writer fence | Source verified (trigger) | Actual shell mutation/installer consumers, source on legacy branch |
| `.github/workflows/main-agent-model-routing-acceptance.yml` | `core/integration` push/manual | Acceptance Workflow can be a publication carrier; classify whether it writes | Source verified (trigger) | Exact side effects and operator identity |
| `.github/workflows/deploy-realm-fabric-fenced.yml` | main push/manual; Action Relay install_release | Calls existing Realm deployment action, but original source includes a literal pinned commit | Source verified | Current exact desired generation claim provenance and active deployment |
| `agentos_node/action_relay.py` | Registered `agentos.realm-fabric.claim_deployment`, `advance_deployment`, `renew_deployment`, `release_deployment`, `install_release` | Existing `core-deployment.json` plus `core-deployment.lock`, generation/lease/install checks (see `docs/CORE_DEPLOYMENT_AUTHORITY.md`) | Source verified | Caller-supplied lease_owner is not authenticated ONE approval; actual loaded relay version; OS privilege containment |
| `agent_core/runtime_converge_contract.py` | `node.runtime.converge` source allowlist | Pinned `ALLOWED_SOURCE_REFS = {"core/integration"}` at baseline | Source verified | Migration to main-only without breaking older Client/Runner rollout |
| `agentos_node/runtime_converge_action_relay.py` | Direct fetch/checkout/runtime converge | Separate side-effect writer, not covered by Realm-only lock by assumption | Source verified | Privileged ingress ownership, scope, independent fencing and rollback |
| `agentos_node/bootstrap_control.py` | Installer/bootstrap script execution | Script fetch and execution can be an effect boundary | Prior source audit; re-read required | Exact entry routing, credentials and allowed operations |

The table deliberately distinguishes **observed source** from **live producer**, and a lock protecting Realm Fabric from a lock protecting every service.

## Census / scope accounting

- A fresh Git tree read of the pinned `main` returned **3,168 paths**, not truncated.
- The same tree contained **617 `.github/workflows/*.yml` files** (file inventory, not claim of active or write-capable Workflows).
- Previous #2366 review evidence reported, for an explicitly different pinned legacy-branch snapshot, **449 executable legacy Workflow roots**, **254** with integration Push and **122** with static potential side-effect patterns. These figures are **prior evidence requiring regeneration**, not present-day verified state or proof that all are active.
- Any Workflow not yet classified is **UNKNOWN**, never implicitly SAFE; build a complete provider-ID/workflow-path/branch/trigger/action/capability/credential matrix, with provider status and effective target identity.

## Machine-readable baseline census — evidence update

Companion source inventory: `docs/governance/1682-workflow-source-census-20261122.json` (pinned Git blob SHAs, paths, triage and evidence strength).

- **617 / 617** Workflow YAML paths have been enumerated from the pinned `main` tree, without truncation.
- **23 / 617** selected higher-priority Workflow sources have undergone *limited static pattern scans*; **594 / 617** remain explicitly `unreviewed`.
- Filename-only triage: 188 priority-1 candidates, 289 priority-2 candidates, 140 priority-3 candidates. These are **queue priorities**, not write-capability or active-state verdicts.
- A limited static scan found explicit SSH/systemctl/sudo tokens in Core Bundle, Core deploy, invoice intake, employee recovery, and other paths. A zero-match file is **not** evidence of no effects: workflow steps may call external scripts/capabilities.
- **Provider status evidence recovered via existing scanner:** the generic GitHub fetch endpoint refused the repository-wide Actions Workflow listing, but existing read-only `legacy-workflow-publisher-inventory.yml` CI queried provider state through its constrained GitHub Actions token. Provider flags still require independent branch/credential and Oracle readback verification.
- **Oracle state blocker:** runtime-loaded unit, real principals, direct write privileges and rescue availability have not been read back from Oracle.

Next G0 work must reconcile source paths **and** GitHub provider workflow identity, plus indirect effects through reusable Workflows, Action Relay jobs, remote scripts and other repositories. Source scanning alone cannot complete the active-publisher census.

## Reused existing whole-tree and provider census (not a new scanner)

Existing Draft PR #2366 contains a read-only complete Workflow scanner, a cross-branch comparator, provider-state reader, recent-run reader, tests and the `legacy-workflow-publisher-inventory.yml` CI. **Reuse these existing implementations**, rather than expanding the manually scanned 23-file sample or building a competing scanner.

Successful [CI run 45000061954](https://github.com/alston-personal/agentmanager/actions/runs/45000061954) scanned pinned `main@77138a48` and `core/integration@8c49a4de`, and uploaded [full JSON evidence artifact](https://github.com/alston-personal/agentmanager/actions/runs/45000061954/artifacts/14745183548). Checked machine-readable summary: `docs/governance/1682-existing-publisher-ci-evidence-20261122.json`.

| Static source evidence | Pinned main | Pinned core/integration |
|---|---:|---:|
| YAML files, including four nested historical paths | 617 | 453 |
| Root Workflow paths | 613 | 449 |
| Root `core/integration` Push candidates | 248 | 254 |
| Root legacy Push + potential mutation signals | 119 | 122 |
| All potential mutation-signal classifications | 267 | 215 |
| Manual-review-required classification | 176 | 114 |
| No mutation signal observed (NOT proven safe) | 174 | 124 |

Provider reader observed **1,076 Workflow identity paths**, **122** legacy Push/mutation candidates flagged active, and **463** active provider identities outside the two pinned source trees. Those 463 are **not proven executable publishers**. Static branch comparison: 449 shared root paths, 49 changed source versions, 164 main-only paths, 10 divergent legacy mutating Push candidates. Previous quarantine list had 150 paths, and the scanner identified **119** potentially mutating legacy Push paths outside that list; this does not justify blindly disabling any workflow.

The recent-run reader observed 1,502 run records, including 502 on legacy branch and 16 recent candidate legacy Push runs; **pagination was incomplete**. These values are observations, not an exhaustive run census.

**Open G0 boundaries:** verify each provider ID's branch reachability, usable credentials and executor owner, investigate script/reusable-workflow/other-repository indirect mutation, verify Oracle installed runtime, privileged OS write boundaries and rescue permissions. The scanner is based on static source signals, not actual Oracle deploy success or proof of safety.

## Provider identity triage with direct artifact readback

The full [read-only Workflow artifact](https://github.com/alston-personal/agentmanager/actions/runs/45000061954/artifacts/14745183548) was retrieved and inspected, not just its CI log summary. Its `workflow-recent-run-triage.json` identifies **16 distinct provider Workflow IDs** with sampled `core/integration` Push runs and source-level potential mutation signals. The combined observations total **70 Push runs**, of which **25** belong to **`oracle-core-bundle-immutable-runtime-convergence.yml` (Workflow ID `375122039`, last observed 2026-11-22 07:50:42 UTC)**. These are Actions run observations, **not 70 verified Oracle writes**. Exact 16 Workflow IDs, paths, observation counts and still-unknown live authority fields are preserved in `docs/governance/1682-observed-legacy-push-p0-20261122.json`.

The 463 provider-active identities absent from *both pinned source root trees* have now been separated into mutually exclusive **filename-only** review queues (NOT capability or risk conclusions):

| Review queue (first filename match wins) | Provider-only identities |
|---|---:|
| deploy/release/rollout/publish/cutover | 53 |
| repair/recover/rollback/patch | 41 |
| install/bootstrap/provision/activate | 13 |
| runtime/relay/executor/scheduler/node | 41 |
| audit/inspect/diagnostic/acceptance/guard | 165 |
| no keyword match | 150 |
| **Total** | **463** |

The run-history sample observed one provider-only path, `legacy-workflow-publisher-inventory.yml`, with 50 runs outside the old branch; the sample has incomplete pagination, so **the other 462 must not be called inactive**. Neither an active provider flag nor a suggestive name proves present branch-trigger reachability. Some source files may have existed only on older deleted branches, while others may still be referenced indirectly.

**Next G0 proof:** verify the 16 observed P0 Workflow IDs' precise run jobs, invocation/credentials and Oracle mutation Receipts; reconcile the 463 provider-only paths to GitHub branch refs, callable-workflow references and provider states, with rescue-critical paths classified before any disable action.

## ONE live selector versus Oracle runtime evidence — read-only query

A live `agentos_project_state("agentos-core")` query at this checkpoint returned the ONE active selector `idx-core-20261122T080116Z-be9333bf` / IR `ir_20261122T080116Z_be9333bf`. Its current goal concerns Windows `vopc5750` Thin Client retirement, **not** this #1682 publisher inventory. Separately, `agentos_resume("agentos-core")` returned an older November 6 submitted task and IR `ir_440756444cbc47d39ab5a5acd4eefaad`. These are different views/continuations, and neither should be overwritten or interpreted as an Oracle deployment receipt.

The connected AgentOS MCP methods available in this chat (`agentos_project_state`, `agentos_resume`, `agentos_task`, `agentos_advance_ir`) **do not provide a dedicated, authenticated Oracle systemd/current-release/permission inspection method**. Therefore G0 Oracle runtime/PID/OS write boundary and recovery evidence remains **UNVERIFIED**. Existing Oracle inspection through an independently authorized runtime provider or known read-only Workflow is required. Do not use `agentos_advance_ir` to repurpose an unrelated active selector merely to record a source audit.

## Historical Oracle effect confirmed, distinct from current loaded state

Existing Core Bundle Workflow `converge` runs on `core/integration` Push and on eligible manual dispatch. Pinned `main` workflow at lines 162–190 accepts `github.sha` as the remote `SOURCE_COMMIT`, via SSH using deployment secrets, before Worktree/installer/systemd mutations. Its `publish-convergence-receipt` job sets `oracle_runtime_verified=true` from `needs.converge.result == success`; the field is **not** independently backed by a separate live-version query at receipt publishing time.

Read back **historical [2026-11-09 Run #42576789610](https://github.com/alston-personal/agentmanager/actions/runs/42576789610), converge Job #129026198176: SUCCESS**. Its actual Job log records `Preparing worktree (detached HEAD f9d6c93d)`, `core_bundle_install_services=DONE`, `core_bundle_lobster_restart=DONE`, service runtime immutable path checks and `core_bundle_immutable_runtime=PASS`, for SHA `f9d6c93d004e8adb712953be46a10eb36dabb393`. This verifies **historical remote install/service changes and within-run runtime check**, stronger than a static candidate. Record: `docs/governance/1682-historical-oracle-core-bundle-effect-20261122.json`.

By contrast, 2026-11-22 PR-triggered [Run #44999152955](https://github.com/alston-personal/agentmanager/actions/runs/44999152955) reported `converge=skipped`, with only the read-only preflight passing. A published GitHub receipt for this run has `oracle_runtime_verified=false`. A PR CI PASS therefore must not be counted as a deployment.

**G0 remaining blocker:** no direct authoritative Oracle loaded-PID/version/perms readback for 2026-11-22, no proof that old SSH credentials still work or have been revoked, no verified ONE approval link. The historical successful write makes the potential bypass concrete, but does **not** prove an ongoing overwrite today or authorize switching off any workflow without rescue acceptance.

## Oracle read-only inspection entrypoints: source-level classification

The pinned main tree contains existing Oracle inspection flows; a new runtime inspector is not automatically necessary. Detailed candidate classification and disclaimers are in `docs/governance/1682-oracle-inspection-route-review-20261122.json`.

- `oracle-core-service-runtime-audit.yml` includes a read-only SSH audit job that inspects `runtime/core/current`, systemd `MainPID`/`WorkingDirectory`/`ActiveState` and `/proc/PID/cwd`; it is a potential source for an **independently timestamped Oracle runtime readback** after its entire workflow is reviewed and executed under existing authorized governance.
- `core-realm-fabric-live-fingerprint-20261012.yml` reads the Realm Fabric live process cwd, user systemd properties and current symlink.
- `oracle-inspect-agentos-core-project-state.yml` reads project state on an Oracle self-hosted runner, **not** all loaded executable versions.
- **Do not call** `oracle-diagnose-action-relay-runtime.yml` a safe read-only inspector: after its process diagnostics it runs `git fetch origin main`, `git reset --hard origin/main` and locally commits a diagnostic file. Its spool/capsule printing also requires a privacy/sanitization review. This is a source-level observation, not evidence a direct production push succeeded.

The existing `agentos-core` MCP offers continuation/IR readings, not a dedicated Oracle loaded-PID and OS-write-permission attestation. No Workflow dispatch was executed during this G0 read-only audit. Runtime truth for **current** 2026-11-22 still needs an independently authorized Oracle readback; do not substitute historical successful deployments or source-only checks for that receipt.

## Historical Team drift reconciled — no repeat fix

Read-only comparison of accepted prior Oracle evidence and subsequent actual job logs:
- Oct 6 full Core audit [run 37394284772](https://github.com/alston-personal/agentmanager/actions/runs/37394284772): ten immutable service paths, zero mutable.
- Nov 9 Core Bundle historical SSH deploy [run 42576789610](https://github.com/alston-personal/agentmanager/actions/runs/42576789610): installed immutable SHA `f9d6c93d...`, restarted services, checked runtime.
- Nov 15 full Core audit [run 43657091837](https://github.com/alston-personal/agentmanager/actions/runs/43657091837), job 132637918255: **9 immutable / 1 mutable**; the mutable service was `teams-commander.service`, while `os-lobster` and several others were `inactive` (service health is not part of this path audit). This historical deviation was **already recorded and investigated** in #1682, not a new root-cause discovery.
- Nov 21 21:05Z / **Nov 22 05:05 Taiwan** read-only Teams preflight [run 44949671719](https://github.com/alston-personal/agentmanager/actions/runs/44949671719), job 136984604799: `owner_class=validated_immutable_release`, eight checks true, `converge` and `teams-immutable-cutover` skipped. This newer observation **supersedes the Nov 15 Teams-only mutable evidence**; it does not attest all ten Core services or prove that the new release was deployed by this PR.
- Existing #1682 work already included merged Teams guards (#2311, #2312, #2313) and the new read-only acceptance in Draft #2366. **Do not implement another Teams migration** based solely on the old 9/10 audit.

**Credential authority mismatch that still requires review:** the *read-only-labeled* `oracle-core-service-runtime-audit.yml` and mutating `oracle-core-bundle-immutable-runtime-convergence.yml` both reference the exact same `AGENTOS_DEPLOY_SSH_KEY || N8N_DEPLOY_SSH_KEY` and user/port secrets for hosted SSH. Read-only **commands** do not imply a read-only **principal**. The effective SSH forced-command/Unix/sudo/file permissions and trust of PR-triggered workflow source must be independently attested. No credential exposure is asserted, and no SSH credential was used in this audit.

Evidence matrix: `docs/governance/1682-oracle-runtime-temporal-reconciliation-20261122.json`. Current full-Core runtime and audit-principal privileges remain **UNKNOWN**.

## G1 preliminary writer authority matrix (G0 is still open)

A machine-readable **source-to-identity-to-side-effect boundary** matrix is now in `docs/governance/1682-writer-authority-matrix-20261122.json`. It reuses the existing Realm deployment lease authority and inventories independent writers; it does **not** propose a new release store or grant publication permission.

| Writer/inspector | Identity boundary | Mutated or inspected target | Gap |
|---|---|---|---|
| Legacy Core Bundle `converge` | Hosted GitHub Actions SSH deploy secret/user | Core Worktrees, systemd, current symlink | Historical mutation proven; present approval and target fencing unverified |
| Core runtime SSH audit | **Same SSH secret/user expression** as deployment job | Core version, service cwd/PID (read-only commands) | Same expression is not evidence of a distinct read-only principal; actual credential and sudo scope unverified |
| Manual safe Chronos rescue | SSH as `ubuntu` enforced in preflight | Action Relay/Chronos owner-managed repair | Preserve independent rescue; live fallback and permission acceptance pending |
| Realm Fabric Action Relay | Unix owner/group capsule; caller-supplied lease label | Realm-specific release, existing `core-deployment.json` | Lock/CAS exists; mandatory authenticated ONE intent and loaded-version coverage unverified |
| Runtime Converge Action Relay | Oracle ubuntu execution | Git checkout/runtime effects | Distinct write path; not proven fenced by Realm generation |
| Oracle self-hosted permission audit | Self-hosted runner identity | Governance Directory metadata | Read-only commands, but runner effective write privileges unknown |
| Action Relay diagnostics | Self-hosted runner | Git checkout and diagnostic file | Contains `git reset --hard` / `git commit`; **not** a safe read-only inspection carrier |

The existing [`oracle-attest-governance-permissions.yml`](https://github.com/alston-personal/agentmanager/blob/main/.github/workflows/oracle-attest-governance-permissions.yml) reads **Governance Directory path ACL**, not the whole production release, systemd and SSH principal permission envelope. It cannot close the publisher authorization gate on its own.

**Credential inference limitation:** audit and deployment share the *same source-level fallback names*, but the effective secret value, exact SSH login privileges, forced commands and `sudo` policy are not observed. Do not claim identical effective privileges, privilege abuse, or current writer ability until sanitized owner-authenticated readback.

**G1 entry rule:** map every mutating ingress to one trustworthy exact-operation ONE approval and target-side CAS/fencing boundary, then independently test old Client/GitHub/Runner bypass attempts. Await G0 provider and Oracle reconciliation before promoting this preliminary matrix to an accepted integrated design.

## Pre-existing capabilities to reuse

- Realm Fabric immutable deployment authority: `docs/CORE_DEPLOYMENT_AUTHORITY.md` and its effective Action Relay.
- Protected-branch authority: `AGENTS.md`, `scripts/protected_branch_authority.py`.
- Existing engineering authority and documentation-reality gates, not a new scheduler/state machine.
- Governance proposal PR #2367 (separate, Draft): inventory-first PR CI admission; no authorization power.
- PR #2366 (separate, Draft): release-intent preflight, SQLite generation prototype and main-only Workflow proposals; **must not install SQLite as a second independent authority** without a single-state design and verified migration.

## Authority model to resolve before implementation

1. **Approval:** locate and verify a genuinely authenticated ONE publication-approval record, including exact project, Realm, environment, operation, principal, immutable artifact, source SHA, expiry and human approval Receipt.
2. **Identity:** establish which caller identities are allowed to request versus execute; a caller-supplied `lease_owner` or `Decision` object is not proof.
3. **Admission:** classify each entry (including recovery, SSH, Workflow dispatch, Action Relay, direct systemd/Git/file writers) and route production effect through one privileged target enforcement boundary.
4. **Concurrency:** reconcile Realm Fabric existing generation and other services' generations, stale-client support and pending CAS; do not introduce multiple independently writable release heads.
5. **Physical isolation:** test OS file, systemd, sudo, SSH, Worktree, GitHub provider permissions; a rejected controller request is not safety if the same executor can write directly.
6. **Rollback:** verify backups/restore of immutable Worktree, service units, state/SQLite/WAL if used, capability markers, symlinks and live PID/health; rescue channel alternation must be proven, not assumed.
7. **Publication lifecycle:** identify GitHub workflow identities on legacy `core/integration`, preserve at least one verified rescue path, perform controlled quarantine only after separately authorized operator approval.

## Open risks / mandatory negative tests

- Same-owner lease replay, released or expired lease reuse, stale receipt replay.
- Valid SHA with mismatched artifact digest, approval receipt, Realm, operation or principal.
- Two Executors competing for same target, plus an old executable ignoring the new gate.
- DB commit successful but notification lost; process dies after Worktree/systemd mutation.
- Version drift between running Oracle process, installed files and claimed Git main.
- Recovery update simultaneously disables normal and rescue transports.
- GitHub Workflow disabled at provider scope while rescue flow still depends on it.
- Direct `core/integration` push triggers old Workflow while main-only patch passes CI.

## Required evidence and acceptance gates

| Gate | Exit criterion | Status |
|---|---|---|
| G0 Scope census | Full executable workflow identity + target mutation inventory with coverage counts | OPEN |
| G1 Authority graph | ONE approval issuer/reader, identities, single writer and State ownership documented and independently reviewed | OPEN |
| G2 Design | Reuse/retire matrix, migration order, client compatibility and failure injection design reviewed | OPEN |
| G3 Implementation | Controlled code PRs based on latest protected main and no independent duplicate authority | BLOCKED until G0–G2 |
| G4 Offline tests | Adversarial replay/concurrency/rollback and bypass negatives PASS | NOT STARTED for unified design |
| G5 Oracle acceptance | Read back exact loaded PID, unit, target version, rollout and rollback/rescue Receipts | NOT STARTED |
| G6 Legacy quarantine | Provider-side branch/Workflow quarantine with independent operator Receipt, no loss of rescue | NOT STARTED |

## Immediate continuation

1. Expand this table with **every active / retired / historical workflow identity** and all actual mutation operations; attribute each to an exact service/root and operator permission.
2. Read actual Oracle installed Action Relay version and governance state through the existing authorized inspection route, without changing live state.
3. Review architecture, security and reliability model together, then create **one** bounded implementation plan; decompose PR #2366 only after this inventory is reconciled.
4. Do not merge or deploy #2366 on the basis of an isolated green CI, and do not push to or disable the old branch before safe rescue/authorization proofs.

Unknown does not mean failure, but unknown must block a claim of production safety.
