# AgentOS Current Architecture & Reality

**Status date:** 2026-10-02  
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
| Runtime ownership isolation | Implemented policy + CI guard; Dashboard immutable-runtime migration candidate | `.agent/governance/runtime_ownership.json`, `scripts/check_runtime_ownership.py`, `scripts/deploy_dashboard_release.sh` | `tests/test_runtime_ownership.py`, `Runtime and Completion Governance`, issue #470 |
| Durable work completion ownership | Implemented + live accepted | `scripts/work_completion.py`, Lobster integration in `scripts/lobster.py`, immutable completion-executor runtime | `tests/test_work_completion.py`, Oracle run `36130001931`, issue #470 |
| Pinned project POC candidate deployment | Implemented for LayoutLib candidate path | `.github/workflows/oracle-release-layoutlab-v08-dev.yml` | release-lane static acceptance + public POC acceptance after dispatch |
| Node registry / capability discovery | Implemented + tested | `agent_core/node_registry.py`, `scripts/agentos_node.py` | `tests/test_agentos_node.py`, `tests/test_node_registry_v01.py` |
| Web static index render capability | Implemented candidate + tested | `capabilities/web_static_index/`, `scripts/web_static_index.py`, `agent_core/capability_manifest_adapter.py` | `tests/test_web_static_index.py`, `tests/test_capability_manifest_adapter.py` |
| Google Colab remote compute provider | Declared integration candidate | `capabilities/colab_compute/capability-manifest.json`, `docs/COLAB_GPU_PROVIDER.md` | live Oracle preflight/session/output receipt required |
| MiniMax H3 video generation via Colab | Declared integration candidate | `capabilities/minimax_h3_colab/capability-manifest.json`, upstream `killkli/minimax-h3-colab-skill` | pinned upstream install + end-to-end MP4 receipt required |
| Governance responsibility resolution | Implemented + tested | `agent_core/governance_directory.py` | `tests/test_governance_directory.py`, governance audit workflow/evidence |
| Resource registry / world-state lookup | Implemented + tested | `agent_core/resource_registry.py` | `tests/test_resource_registry.py` |
| Realm / cross-node fabric | Implemented slices + tested | `agent_core/realm_fabric.py`, `agent_core/realm_server.py`, `agent_core/realm_cli.py` | `tests/test_realm_fabric.py`, `.agentos/commands/` |
| Controller dispatch route | Implemented + tested; capability-first selection candidate | `agent_core/controller_service.py`, Realm server `/v1/controller/dispatch` | `tests/test_controller_service.py`; historical Control Inbox evidence proves the route, while capability-auto routing still requires post-merge live acceptance |
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

### Mio PDCA social observation (#814 candidate)

The currently deployed Persona PDCA sources are on `main`, separately from
the historical Social Runtime patrol workflow on `core/integration`. Do not
infer live PDCA acceptance from a manual patrol run or from either branch head.

`persona_pdca_tick.py` now queues `social.threads.observe` as `pending_external`.
Follow-up candidate: each active, sufficiently energized PDCA heartbeat also
plans a read when the last successful, receipt-linked read would exceed the
freshness goal before the next heartbeat. `social_observation.max_age_minutes`
defaults to `heartbeat_minutes` (60 if omitted); periodic observation can be
disabled with `social_observation.enabled=false`. Invalid interval policy does
not schedule a supplemental read. This environmental input does not replace
the randomly selected creative/reflection intent or compel a public reply.
Sleep/rest and energy below 15 defer periodic reads; an existing candidate or
in-progress read prevents duplicates, and a blocked read prevents supplemental
retry until repair. An explicitly selected observe remains a separate decision.
If all 12 pending slots hold unfinished work, supplemental observation is
deferred with `pending_capacity`; only terminal entries may be evicted for it.
The passive read cost is accounted in energy, and the existing worker prioritizes
the queued observation over a public write candidate. No new timer is introduced.
Freshness is a planning goal sampled at heartbeats, not a wall-clock SLA through
rest, adapter outages or worker backlog. This follow-up is source-tested only;
merge/deployment and a real autonomous read receipt remain required.
The existing short-cycle `run_persona_social_actions_user.sh` consumes that
durable intent through `persona_social_executor.py` and the existing Social
Runtime `post.read` / `replies.read` boundary. It never uses Threads Web DM.
No read, failed required reads, or malformed adapter result cannot produce a
completed observation. The executor stores action/cycle-bound receipts, a
cursor, and a separate last-observation summary. It queues `social.reply.review`
only after fresh externally authored replies are observed. Newest five posts
are read even when `has_replies=false`; the bounded scan covers at most 20 posts
and newly eligible replies at most 42 hours old. It does not prove exhaustive
historical/paginated coverage or successful autonomous reply delivery.

Read failure records BLOCKED plus an open, sanitized Persona incident in the
data layer; the heartbeat and other work continue. These local incidents are
pending repair, not proof that GitHub Incident/repair routing completed.
The public activity projection exposes the last actual read status/time/counts
separately from the heartbeat without comment text, binding IDs or credentials.

This candidate uses the existing Oracle-local social worker lane. The unified
AgentOS scheduler route, owner Observer parity, automatic repair routing and
live new-comment acceptance in #814 remain pending. Offline tests prove only
the source contract. Merge approval and exact-generation Oracle deployment
must precede any live-restored claim.


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

`scripts/deploy_dashboard_release.sh` owns the release switch, exact listener verification, canary, PM2 replacement, rollback, auth/admin route checks and a regression probe that temporarily removes only the legacy shared `.next` build. A release is accepted only if the public protected routes remain healthy while that legacy build is absent. Until the first successful Oracle receipt, the registry marks this Dashboard migration as candidate rather than live.

## Windows Thin Client self-update receipt boundary

As of 2026-10-06, governed Thin Client upgrades initiated through ONE must not execute the installer inline inside the same `shell.exec` task that is expected to report the rollout receipt. The Windows installer intentionally stops the existing Thin Client process before replacing runtime files; if invoked inline, that process can terminate itself before it submits the task receipt.

The canonical rollout pattern is therefore two-stage: ONE asks the current Thin Client to register a delayed, one-shot Windows Scheduled Task pinned to an immutable source commit; that scheduling action returns a receipt first. The deferred updater then stops/replaces/restarts the Thin Client independently. Live acceptance waits for a fresh heartbeat and only then invokes the new capability. This keeps GitHub Actions as a deployment trigger/audit surface while Windows execution and acceptance continue through ControllerService/ONE.

## Windows one-click node onboarding

The canonical Windows onboarding entry point is `install-agentos.cmd`, backed by `install-agentos.ps1`. A user starts the installer once. The bootstrap resolves an immutable source commit, ensures a real Python 3 interpreter is available, installs the Thin Client files, preserves any existing enrollment identity, and configures the per-user `AgentOS Thin Client` Scheduled Task. The scheduled task is headless: it launches a hidden PowerShell runner rather than a visible `cmd.exe`, so logon starts, watchdog restarts, and task restarts must not flash a console window in the interactive desktop session. Upgrades also remove obsolete `AgentOS Thin Client Watchdog` and `AgentOS Thin Client Headless Switch` tasks from earlier builds, and the successful `.cmd` bootstrap exits automatically instead of pausing in a visible console.

A fresh machine may require one Realm enrollment approval. That approval is the intentional trust boundary: the installer displays the bounded enrollment code and waits for approval, then continues automatically in the same invocation. It must not require a second installer run merely to enable autostart. A machine with an existing `state/client.json` must preserve that identity and token, skip re-enrollment, repair/restart the background task, and proceed directly to readiness verification.

Acceptance is end-to-end rather than file-copy success. The installer only reports `AGENTOS_ONE_CLICK_INSTALL=PASS` after the background Thin Client remains running and `agentos-client verify` succeeds against ONE. The installer may auto-install Python through winget when Python is absent, but Windows Store App Execution Alias stubs are not accepted as a valid interpreter.

## Studio Web production serving authority

As of the 2026-10-02 live Oracle nginx audit, the TLS server for `studio.milkcat.org:443` still serves its default static root from `/home/ubuntu/zeus-writer/website/dist` with `try_files $uri $uri/ /index.html`. This is current observed serving topology, not source-of-truth ownership.

`alston-personal/studio-web` is the canonical platform website source for the extracted shell and root-owned artifacts. The historical `oracle-cutover-milkcat-world-home.yml` did not change nginx root; it built a pinned `studio-web` commit and copied selected generated artifacts into the existing live dist. Therefore earlier language calling that operation a "cutover" referred to content publication, not a serving-root migration.

The legacy Action Relay capability `site.sync_build` is retired from mutation authority and now fails closed rather than fetching/building Zeus Writer. Production publication from `studio-web` must use the governed Studio Web release path. A future nginx-root migration is a separate change and must preserve the route ownership matrix and independent aliases/proxies.

## Hosted Participant enrollment control lane

As of 2026-10-02, the existing Oracle Realm enrollment control workflow is being generalized to carry Participant join requests without creating a second direct-Oracle workflow. Enrollment mutations execute only from `main`; feature-branch pushes may run governance checks but must not create, approve, challenge, or claim live Participants.

For hosted Participant join requests, ONE-issued `claim_secret` is stored only under `/home/ubuntu/agent-data/runtime/participant-enrollment/` and is never committed or printed. The directory/file ACL is limited to the trusted `agentos` service group (`0750` directory, `0640` state file) so the `agentos-node` enrollment ingress can hand the credential to the `ubuntu` GUI Host Runtime without making it world-readable. Repository evidence may contain only non-secret correlation fields such as Participant ID, request ID, user code, negotiated protocol, expiry, and challenge.

The initial live Gemini Web join request proved that the Participant runtime endpoint is reachable and can negotiate protocol 1.0. That request remains an experiment artifact; acceptance does not advance above A0 until the actual Gemini Participant returns the correlated challenge response and ONE records verification.

## Participant runtime enrollment

As of 2026-10-02, Participant Protocol enrollment is implemented as a generic ONE runtime surface rather than documentation-only guidance. The first runtime slice supports hosted or direct Participants without provider-specific Core logic.

Implemented endpoints:

- `POST /v1/participants/join/request`
- `POST /v1/participants/join/status`
- `POST /v1/participants/join/claim`
- `GET /v1/participants/describe?participant_id=...` with Participant bearer credential

ONE negotiates the highest common supported Participant Protocol version from the currently supported set (`1.0`). Enrollment uses a pending request + correlated Participant challenge response + operator approval + claim flow. The challenge response must echo the ONE-issued `request_id`, stable `participant_id`, exact challenge, negotiated protocol, and `ack: ACCEPT`; claim is rejected until ONE records challenge verification. Operator approval is available through `agentos-one participant-approve --code ...`. Claimed enrollment records stable Participant identity separately from `host_runtime_id` and issues a Participant credential to the Host Runtime.

Enrollment/negotiation may advance a Participant to A3 only. Core conformance, capability verification, ONE-routed execution, correlated receipts, and A7 READY remain separate runtime work and must not be inferred from successful enrollment. Missing required v1.0 methods (for example `shutdown`) are preserved explicitly after enrollment.

The first Gemini Web experiment remains A0 until the new runtime surface is deployed and a Host Runtime submits/claims a real enrollment request. This implementation is generic and must be reused by future model, Agent, service, browser, and Executor Participants.

## Capability-first dispatch ingress

As of 2026-10-02, the ControllerService source contract no longer requires normal callers to provide a concrete node identifier. A caller may submit only an action/capability. ONE then considers online nodes advertising that capability and deterministically prefers lower pending queue depth, then fresher heartbeat, then stable node ID. Explicit `node_id` targeting remains available for diagnostics, conformance, break-glass recovery, or work whose semantics truly require a specific physical target.

This is an implemented and source-tested scheduling step, not yet proof that all production workflows use it. A large grandfathered set of GitHub workflows still encodes `runs-on: [self-hosted, Linux, ARM64, oracle]`; `.agentos/governance/main-legacy-direct-oracle-workflows.txt` is therefore a retirement list, not evidence that migration is complete. New direct-Oracle workflow paths are rejected by `Main Runner Window Guard`.

The canonical caller rule is documented in `docs/DISPATCH_INGRESS.md`: GitHub Actions is an ingress/transport and must not become the scheduler. The target runtime topology is caller → ONE dispatch ingress → capability/policy/load selection → Participant/Node/Executor → correlated receipt. Full production acceptance still requires migrating representative legacy workflows and proving that unrelated jobs no longer block one another merely because they historically shared an Oracle runner label.

## Realm Node Map and capability semantics

The Realm Node Map is persistent ONE-side state. A node record may include heartbeat freshness, reported/effective status, capabilities, tool presence, and surface inventory.

Important distinctions:

- a conceptual/logical surface is not automatically an enrolled live node;
- a capability advertised by a node is not authority to execute it;
- transport reachability is not the same as capability availability;
- reaching ControllerService and receiving a node-level capability error proves the Core dispatch route is alive even though the target node is not yet ready for that action.

The authoritative live node count/status comes from the runtime NodeRegistry, not from architecture diagrams or conversation assumptions.

### Hosted node readiness verification

A freshly enrolled client may complete its readiness regression without requiring an operator to paste a local verification command. The bounded command surface is `.agentos/commands/realm-node-readiness-verify.json`; it names only the target node and an idempotency nonce. The hosted carrier validates that fixed schema, enters Oracle through the existing restricted deploy SSH identity, and uses the live `NodeRegistry` plus `RealmFabricStore` as the execution authority.

The carrier may queue only the fixed local `agentos-client verify` operation through the node's already-advertised `shell.exec` capability. It must require the node to be freshly online, require an allowed readable workspace, and wait for the ordinary Realm node receipt. Acceptance requires a zero process return code plus `node_ready:true`, the expected Realm and node identities, and `benchmark_persisted:true`. Node tokens are never read from Oracle, copied into GitHub Actions, or printed as evidence.

This path preserves the authority boundary: GitHub Hosted Actions is transport/orchestration only; Oracle Core owns node registry and task queuing; the enrolled client enforces its local execution policy; the resulting Realm receipt and persisted readiness benchmark are the end-to-end evidence. If the node is offline, the carrier fails closed rather than bypassing the local lifecycle supervisor or inventing a second control path.

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

## Low-latency interactive GUI execution

The Windows Thin Client now has an explicit low-latency interactive execution path in addition to single-step desktop actions. Idle long-poll waits are state-change driven: an empty task pull does not rewrite Realm state, and the server watches the fabric file signature while idle rather than reparsing/writing it at a fixed 20 Hz cadence.

- `/v1/tasks` accepts bounded `wait_seconds` long polling so an enrolled Node does not need to sleep for the historical five-second polling interval before seeing work.
- the Thin Client keeps heartbeat cadence independent from task delivery and waits for work through the long-poll channel;
- Windows manifests advertise `desktop.plan.execute`;
- `desktop.plan.execute` runs a bounded, allowlisted desktop plan locally on the Node and returns one structured receipt containing per-step status, elapsed time and the failed step when applicable;
- non-ASCII or long `desktop.keyboard` input uses Unicode clipboard paste so GUI execution does not depend on the user's active IME;
- GitHub Actions remains a deployment/governance/audit mechanism and is not the intended per-click interactive runtime.

This is not yet a claim of fully human-equivalent desktop autonomy. WebSocket/SSE transport, desktop session leasing/mutex, cancellation, durable plan checkpoints, semantic Gemini/Threads skills and vision fallback for canvas/WebGL remain follow-up work. See `docs/LOW_LATENCY_GUI_AGENT.md`.

## Governed VOPC5750 multi-agent acceptance

VOPC5750 is an enrolled Windows Realm Node, but surface discovery alone is not sufficient evidence that a local model/IDE provider is operational through AgentOS. The canonical acceptance path now distinguishes discovery from execution:

- `agent.surface.inspect` proves the live Thin Client can report its current Antigravity, Codex, Claude Code and Gemini surfaces.
- Antigravity is considered wired only when its session bridge is ready and an actual governed `agent.session.discover` task returns a Node receipt.
- Codex, Claude Code and Gemini CLI are accepted only after a minimal governed `shell.exec` smoke reaches VOPC5750 through the Controller/Realm task transport and the expected response marker is observed in the returned receipt.
- Acceptance evidence is sanitized and uploaded as a workflow artifact. The acceptance workflow must not push evidence directly to protected `main`; source changes and promotions remain PR-governed.
- A provider that is merely installed/running but has no working AgentOS invocation path must be reported as `NOT_WIRED` or `FAIL`, never promoted to READY from presence alone.

The reusable probe lives in `scripts/vopc5750_multi_agent_acceptance.py` and is triggered by `.agentos/commands/vopc5750-multi-agent-acceptance.json` or changes to its workflow/probe definition.

## Windows Node self-healing lifecycle

A Windows Node must not be considered durable merely because enrollment succeeded or the Thin Client process started once.

The canonical Windows one-click supervisor now uses two independent Scheduled Tasks:

- `AgentOS Thin Client`: the hidden interactive-user Thin Client that owns Realm heartbeat, task transport and desktop/GUI capabilities.
- `AgentOS Thin Client Watchdog`: a separate one-minute liveness supervisor that does not share process lifetime with the Thin Client.

Every successful Realm heartbeat writes a local non-secret liveness marker at `state/heartbeat.json`. The watchdog evaluates both process/task presence and heartbeat freshness. A missing process/task is restarted on the next watchdog cycle; a still-running client whose heartbeat marker remains stale beyond the bounded threshold is treated as wedged and restarted. Restart attempts are rate-limited and written to the local watchdog log/state so recovery loops remain diagnosable.

This watchdog is an immediate reliability layer, not the final machine lifecycle architecture. The intended next boundary is to separate a machine-level AgentOS Node Daemon (heartbeat, transport, recovery, OTA and health) from the interactive session adapter (desktop, GUI Worker, Antigravity, Codex, Claude and Gemini). Loss of the interactive user session must eventually degrade only interactive capabilities, not make the entire Node disappear from the Realm.

Windows Node Ready therefore requires recovery acceptance in addition to enrollment: process termination and intentional Scheduled Task stop must self-recover without human intervention, fresh heartbeat must return, and a governed task receipt must succeed after recovery.

## Google web media providers

Google Flow and Google Vids are now represented as governed AgentOS media providers rather than assumed API integrations.

- `capability://media.video.generate.google-flow` represents Google Flow as an authenticated web/GUI provider for generative filmmaking.
- `capability://media.video.compose.google-vids` represents Google Vids as an authenticated web/GUI provider for composition, editing and export workflows when those features are available to the active account.
- Both capabilities begin in `declared` lifecycle state. Public reachability alone is not verification.
- The canonical first acceptance is a read-only provider probe through the existing Realm desktop-inspection lane on `vopc5750`. The probe opens only allowlisted Flow and Vids URLs, waits for each page, inspects visible window titles/processes, and records only non-sensitive screenshot metadata after stripping image bytes.
- Probe classification is conservative: `READY`, `AUTH_REQUIRED`, or `UNKNOWN`. It does not generate media, enter credentials, purchase credits, or bypass provider challenges.
- Provider-specific quota discovery and effect execution require later evidence and remain subject to ordinary capability, policy and receipt gates.

The current probe command is carried by `.agentos/commands/realm-desktop-inspect.json`; this reuses an existing governed desktop lane instead of adding another direct Oracle workflow.


## Invoice whole-image comparison candidate

`services/invoice_intake/vision_ocr.py` extends the existing financial-intake reader
with the Gemini Interactions transport previously used only by the benchmark.
`INVOICE_VISION_MODE=off|shadow|primary` defaults to off. Both enabled modes require
`GEMINI_API_KEY` and an explicit `GEMINI_INVOICE_MODEL`; CONFIGURED is not READY.
The existing service deployment reads an optional private
`/home/ubuntu/invoice-intake-service/vision.env` (restrict it to the service owner).
No credentials are committed, copied from another service, or enabled by default.
The provider receives the exact archived image bytes, independently of legacy OCR.
Shadow mode records differences without replacing fields; primary uses validated
vision candidates and always requires human review. Missing credentials, provider
failure and rate limits remain explicit and cannot be presented as vision success.

Buyer, line-item and stamp text/address/contact candidates are preserved in the
existing immutable extraction JSON. The authenticated invoice detail API exposes
`recognition`; no public route or automatic stamp learning is added. Physical
stamp identity remains owned by `document.stamp-recognition`, whose current
contract alone does not prove matching or a populated stamp database.

The local template reader no longer selects the first page-wide tax ID as the
seller of a three-part invoice, and vendor selection excludes the buyer header.
A vendor without sufficient confidence requires review. The legacy stamp fallback
now imports its checksum validator rather than failing when that path executes.

Verification: `tests/test_invoice_vision.py`, existing invoice DB/regression tests,
and the existing public fixture recall gate. Production model quality, credential
availability, frontend consumption of extended fields, and Oracle runtime parity
remain unverified until a pinned rollout and node receipt exist. Run
`python scripts/invoice_vision_benchmark.py --image /path/to/original.jpg --model MODEL --out /private/comparison.json`
to compare the same archived bytes without writing to the production database.
Model responses are provisional evidence, not ground truth; use independent human
labels and additional samples before promoting accuracy claims.

## Read-only ONE runtime inspection trigger

`.agentos/commands/realm-one-runtime-inspect.json` is a bounded read-only trigger for the existing Oracle Realm/ONE inspection carrier. Changing its nonce requests a fresh observation of live identity, processes, listeners, user/system services, the local ONE health surface, Node Map, current shared-checkout HEAD/dirty-count, and a bounded projection of recent runtime-converge Action Relay receipts. Receipt projection excludes raw stdout/stderr, paths, argv, credentials, and free-form error text; only a short error type and allowlisted convergence fields may be emitted.

Inspection evidence is uploaded as a short-retention GitHub Actions artifact. The workflow does not commit or push evidence directly to protected `main`.

On 2026-10-06 this trigger is being used to diagnose the shared Core runtime-convergence failure blocking #200/#470 completion-ownership acceptance for Market Master #1200. A successful inspection is evidence only; it is not a deployment or completion claim.
