# AgentOS Current Architecture & Reality

**Status date:** 2026-08-31  
**Purpose:** canonical public map of what is implemented, what is verified, and what is still research.

This document exists to prevent architecture drift between code and prose. It is intentionally narrower than a roadmap: every item marked **Implemented** must have a concrete repository path; every item marked **Verified** must also have a test or evidence path.

## Product goal

AgentOS has one continuity goal:

> A user should be able to switch session, model, executor, or machine and continue useful work without manually reconstructing the project from a large conversation history.

This goal is broader than memory retrieval. AgentOS treats durable project/working state as an external system concern and treats models as replaceable executors.

## Reality map

| Capability | State | Implementation | Verification / evidence |
|---|---|---|---|
| Logic / data separation | Implemented | `agent_core/config.py`, bootstrap/runtime scripts | existing bootstrap/runtime tests |
| Session close / handoff record | Implemented | `agent_core/session_lifecycle.py`, `runtime_core/` | `tests/test_session_close.py` |
| Continuation-state monotonicity | Implemented + tested | `scripts/continuation_state.py` | `tests/test_continuation_state.py` |
| Persistent control plane | Implemented + tested | `agent_core/control_plane.py` | `tests/test_control_plane.py`, `.agentos/evidence/bootstrap-control-plane.txt` |
| Canonical Project Identity | Implemented + tested | `agent_core/project_store.py`, `agent_core/resolve_facade.py` | `tests/test_project_store_canonical.py`, governed Core registration workflow/evidence |
| Project release-lane authority | Implemented + tested | `.agent/governance/project_release_lanes.yaml`, `scripts/check_project_release_lane.py` | `tests/test_project_release_lane.py`, `Project Release Lane Guard` |
| Runtime ownership isolation | Implemented + Dashboard live accepted; remaining services migrate independently | `.agent/governance/runtime_ownership.json`, `scripts/check_runtime_ownership.py`, `scripts/deploy_dashboard_release.sh` | `tests/test_runtime_ownership.py`, Dashboard run `36197636857`, diagnostic run `36197636810`, issue #470 |
| Durable work completion ownership | Implemented + live accepted | `scripts/work_completion.py`, Lobster integration in `scripts/lobster.py`, immutable completion-executor runtime | `tests/test_work_completion.py`, Oracle run `36130001931`, issue #470 |
| Pinned project POC candidate deployment | Implemented for LayoutLib candidate path | `.github/workflows/oracle-release-layoutlab-v08-dev.yml` | release-lane static acceptance + public POC acceptance after dispatch |
| Node registry / capability discovery | Implemented + tested | `agent_core/node_registry.py`, `scripts/agentos_node.py` | `tests/test_agentos_node.py`, `tests/test_node_registry_v01.py` |
| Web static index render capability | Implemented candidate + tested | `capabilities/web_static_index/`, `scripts/web_static_index.py`, `agent_core/capability_manifest_adapter.py` | `tests/test_web_static_index.py`, `tests/test_capability_manifest_adapter.py` |
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Controller dispatch route | Implemented + live accepted | Realm server / ControllerService path | `.agentos/evidence/issue-64/control-inbox.json`; real Control Inbox acceptance reached ControllerService |
| Core deployment authority / generation fence | Implemented + live accepted | governed claim/install/release path, Action Relay deployment fence | `docs/CORE_DEPLOYMENT_AUTHORITY.md`, active-lease conflict proof, Issue #64 acceptance |
| Platform driver abstraction | Implemented + tested | `agent_core/platform/`, `scripts/platform_runtime.py` | `tests/test_platform_runtime.py` |
| Governance drift guard | Implemented + tested | `scripts/drift_guard.py`, constitution/role registries | `tests/test_drift_guard.py` |
| Protected-branch authority guard | Implemented | `.agent/governance/protected_branches.yaml`, `scripts/protected_branch_authority.py` | `tests/test_protected_branch_authority.py`, `docs/governance/decisions/GOV-2026-08-27-001-protected-branch-authority.md` |
| Evidence-first operational acceptance | Implemented | `.agentos/evidence/` | live acceptance files committed by workflows |
| Documentation Reality Guard | Implemented | `scripts/documentation_reality_guard.py` | `.github/workflows/documentation-reality-guard.yml`, `tests/test_documentation_reality_guard.py` |
| Off-chain Credits ledger | Implemented + tested | `agent_core/credit_ledger.py` | `tests/test_credit_ledger.py`, `tests/test_reuse_before_build_credits.py` |
| Credits pricing + shadow metering | Implemented candidate + tested | `agent_core/credit_service.py`, `.agent/governance/credit_pricing.json` | `tests/test_credit_service.py`, `.github/workflows/credits-contract.yml` |
| Local Credits service boundary | Implemented candidate + tested | `agent_core/credit_http.py` | `tests/test_credit_http.py`, `.github/workflows/credits-contract.yml` |
| Model-independent Cognitive IR | Research | operational handoff envelopes exist, but general sufficiency is not canonical | requires repeatable cross-model continuity benchmark |
| Zero-cost model switch with only `continue` | Target / not yet proven generally | depends on portable working-state + canonical resolution layer | continuity benchmark still required |

## Canonical Project Identity contract

Project identity is explicitly separated from repository, checkout path, runtime path, deployment target, and state storage.

The canonical project document uses schema `agentos.project/v1` and includes at minimum `project_id`, `display_name`, aliases, source repository/branch/path/node, and state locations. `project_id` is a stable logical identity and must not be derived from a repository name or checkout directory.

## Project release-lane authority

Project identity alone does not authorize a branch mutation or deployment. AgentOS Core models project development, promotion, POC deployment, and production deployment as separate authorities.

For LayoutLib the canonical contract is:

```text
active development: alston-personal/layoutlib/develop or explicit feature/fix/governance branch
promotion state:    alston-personal/layoutlib/main
POC surface:        https://studio.milkcat.org/poc/layout-lab/
POC source:         validated, pinned develop candidate
production surface: https://studio.milkcat.org/layout-lab/
production source:  promoted main/release state
immutable baseline: release/v0.7.9
promotion/deploy authority: AgentOS Core
```

A project-development action targeting LayoutLib `main` is denied. Promotion to `main` is a distinct action requiring an explicit human approval event plus Core governance. A passing test, a mergeable PR, a deployment capability, or the user's generic `continue` instruction is not promotion approval.

Project threads may create project commits, tests, evidence, and candidate requests on the development lane. They must not acquire deployment authority by directly editing `agentmanager` deployment workflows. POC deployment consumes a validated candidate commit selected from the registered development branch; production consumes only promoted state. These rules are machine-readable in `.agent/governance/project_release_lanes.yaml` and enforced by `scripts/check_project_release_lane.py`.

For LayoutLib POC deployment, Core additionally requires an exact 40-character `candidate_sha`. The deployment workflow first authorizes `poc_deploy` against `develop`, clones the explicit `develop` branch, verifies the candidate is an ancestor of that branch, checks out the candidate in detached mode, and records both `layoutlib-source-branch=develop` and the exact candidate commit in the public POC document. The release-lane CI guard checks this workflow contract so it cannot silently regress to cloning the repository default branch.

This contract was introduced after the LayoutLib v0.8 development incident in which project development landed directly on project `main` and the project thread then attempted to own Core deployment orchestration. Existing history is not rewritten; the correction establishes the authority boundary from this point forward.

## Runtime ownership and work-completion contract

Production runtime identity is separate from repository checkout identity. The shared Oracle checkout `/home/ubuntu/agentmanager` is a source/cache surface only; it is not a valid authority for deciding which production generation is live. Each service declares a release owner, immutable release root, live pointer and lock namespace in `.agent/governance/runtime_ownership.json`. Newly modified automation is rejected when it adds destructive Git operations against the shared checkout, copies a release into that checkout, or declares a new service runtime directly from it. Existing legacy runtimes are migrated service-by-service rather than silently grandfathered forever.

Promised implementation work is also durable state. Once accepted, a work item remains externally represented until it is either verified Done or explicitly Cancelled. Active work requires an owner, next action, acceptance criteria and an owner lease. A context, chat, model, machine or project switch is represented as a handoff that advances owner generation; it is not completion and it may not erase the work item. While a live owner lease exists, Lobster does not duplicate that work. If the owner disappears and the lease expires, the completion watchdog reclaims the item to `role://completion.controller`, after which it is projected back into the autonomous queue. Blocked work remains owned and records both blocker and next action. Done requires evidence plus a passed verification receipt.

The canonical work ledger is `/home/ubuntu/agent-data/governance/work-items.json` with schema `agentos.work-completion/v1`. `scripts/work_completion.py` performs atomic state transitions and can project unfinished items back into the central `TASK_BOARD.md`. Lobster consumes those `[WI:<id>]` entries before ordinary backlog and may only close the durable item after its existing Inspector/physical-output verification path succeeds. The governed Oracle installation lane is `.github/workflows/oracle-install-completion-controller.yml`; it installs Lobster from an immutable release root and installs a periodic stale-owner watchdog without using the shared checkout as runtime authority. Oracle run `36130001931` accepted the immutable Lobster runtime, active watchdog timer and expired-owner reclaim/projection probe. This closes the failure mode where switching to another project leaves a prior promise as a plan with no executor.

## Dashboard production runtime boundary

The Milkcat Dashboard production process name is `agentos-dashboard`. New Dashboard generations are built from an exact Git commit into service-owned directories below `/home/ubuntu/agent-data/releases/dashboard/apps/`; `/home/ubuntu/agent-data/runtime/dashboard/current` identifies the selected generation. PM2 must run the selected immutable release directory and must not use `/home/ubuntu/agentmanager/dashboard` as its production cwd.

Dashboard secrets and OAuth configuration are configuration state, not source-tree state. The migration controller canonicalizes them in the owner-only file `/home/ubuntu/.config/milkcat/dashboard.env.local`; release builds receive that configuration without logging values. The shared checkout remains a source/cache surface and may move independently.

`scripts/deploy_dashboard_release.sh` owns the release switch, exact listener verification, canary, PM2 replacement, rollback, auth/admin route checks and a regression probe that temporarily removes only the legacy shared `.next` build. A release is accepted only if the public protected routes remain healthy while that legacy build is absent. Oracle run `36197636857` accepted the immutable Dashboard release, PM2 cwd, auth/admin routes, private Fengshui/Tarot summary access and the shared-`.next` independence regression. Read-only run `36197636810` independently confirmed the listener cwd, live pointer and PM2 cwd all resolve to the same service-owned release. The registry therefore marks the Dashboard migration active.


The Completion Controller installer is intentionally **not** triggered by arbitrary edits to the cross-service runtime ownership registry. Its rollout trigger is limited to its own workflow and completion-executor implementation files; changing Dashboard/Fengshui/Tarot ownership metadata must not cause an unrelated Completion Controller reinstall.

## Realm Node Map and capability semantics

The Realm Node Map is persistent ONE-side state. A node record may include heartbeat freshness, reported/effective status, capabilities, tool presence, and surface inventory.

Important distinctions:

- a conceptual/logical surface is not automatically an enrolled live node;
- a capability advertised by a node is not authority to execute it;
- transport reachability is not the same as capability availability;
- reaching ControllerService and receiving a node-level capability error proves the Core dispatch route is alive even though the target node is not yet ready for that action.

The authoritative live node count/status comes from the runtime NodeRegistry, not from architecture diagrams or conversation assumptions.

## Web static-index capability contract

Crawler/AI-friendly public rendering is a reusable capability, not product-specific page code. The canonical capability is `web.static-index.render`, declared by `capabilities/web_static_index/capability-manifest.json` and discoverable through the Governance Directory via the generic manifest adapter.

A web-producing agent or workflow classifies the route, prepares only the already-authorized public page summary as `agentos.web-static-index/v1`, resolves the existing capability under Reuse Before Build, and invokes `scripts/web_static_index.py` (or the manifest-declared equivalent). The capability owns the baseline semantic HTML, escaping, metadata, robots intent and render receipt. Product applications own their dynamic UI and page data; they should not copy or fork the crawler-facing template into each project.

The output is a static initial representation or deterministic public summary/share route. Public-discoverable acceptance requires a render receipt plus a no-JavaScript HTTP inspection. Private/authenticated content is never made public merely to satisfy indexing.

## Core runtime authority status

Realm Fabric is a single live Core service governed by canonical deployment state in `/home/ubuntu/agent-data/governance/core-deployment.json`. The deployment state tracks desired/observed commit, monotonic generation, lease owner/expiry, and deployment status. A live generation is converged only when desired and observed commits match and status is `converged`.

A deployment claim and an installation are separate operations. Installation cannot silently advance generation. While a deployment lease is active, another generation advance is rejected even for the same owner; the current generation must first be released/expired according to the deployment contract.

## Milkcat Credits boundary

Milkcat Credits are an off-chain integer accounting primitive for platform services. The canonical ledger is append-only: grants, reservations, commits, releases, and refunds are immutable entries, while balance and outstanding reservations are projections.

Pricing and settlement are separate concerns. Stable action identifiers resolve through `.agent/governance/credit_pricing.json`. `CreditBilling` supports three explicit rollout modes:

- `off`: quoteable but not metered;
- `shadow`: record intended usage and quoted cost without mutating the credit ledger;
- `enforce`: reserve before execution and commit or release after the service result.

Usage receipts use schema `milkcat.credit-usage-receipt/v1` and are idempotent by account plus operation ID. A loopback-first server-to-server HTTP boundary is provided by `agent_core/credit_http.py`; it exposes health, quote, usage receipt, and account usage-summary operations and can require a bearer token. It does not establish user identity itself. A service integration must not trust a browser-supplied account identity as authorization; the account/subject must come from the platform's trusted identity/session boundary, except for explicitly anonymous shadow subjects during pre-login observation. Zero-cost actions remain zero-cost in enforce mode. Current Fengshui prices are seed values for observation, not a claim of final commercial pricing.

## Important invariants

### Newer user intent must never be rolled back

Compaction, replay, stale tool results, or executor switching must not replace a newer goal/correction with an older one.

### Evidence is not intent

Tool results and execution evidence can inform decisions, but they do not silently rewrite the user's active goal.

### Capability does not imply authority

The presence of a mutation tool, a mergeable pull request, a node capability, or passing CI does not itself authorize mutation. Protected-branch, Core-deployment, project-source, project-release-lane, and effect-level authority remain separate checks.

### Discover before invent

Reusable/cross-project work should resolve existing responsibility, project identity, node capability, resources, and release lane before creating parallel implementations.

### Models are executors, not the durable source of truth

AgentOS does not assume access to model activations or model-specific internal state. Durable coordination and continuity state must remain external and transportable.

### Receipts are first-class evidence

A successful process start, health endpoint, or workflow status is not enough to claim end-to-end correctness. Architecture-sensitive acceptance should preserve capability/action receipts and, when relevant, real transport-path evidence under `.agentos/evidence/`.

## Memory and Cognitive IR boundary

Historical three-layer memory remains a useful conceptual model: L1 immediate/working state, L2 project/continuation state, and L3 stable cross-project knowledge and learned patterns. Current AgentOS separates canonical project state, continuation/work state, governance state, runtime state, receipts/evidence, and validated knowledge.

Model-independent Cognitive IR remains a research hypothesis until repeatable cross-model continuity benchmarks demonstrate preservation of active goal, decisions/constraints, rejected paths, open questions, and next direction.

## Deprecated / historical paths

Historical or compatibility surfaces must not be described as current canonical architecture by themselves, including pulse files/brain dumps as canonical state, repository name as Project Identity, direct GitHub rediscovery as the normal continuation path, process health alone as deployment proof, installer-side implicit generation advance, and project threads directly owning Core deployment orchestration.

## Documentation ownership rule

`README.md`, `ONBOARDING.md`, `AGENTS.md`, `docs/CURRENT_STATE.md`, and `docs/CORE_CONTROL_ROOM.md` are authoritative entry points. Architecture-sensitive implementation changes must update at least one appropriate canonical document in the same change set.

When implementation contradicts this file, fix the file immediately; do not preserve an obsolete narrative for continuity's sake.
