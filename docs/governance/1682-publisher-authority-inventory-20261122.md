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
