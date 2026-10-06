# AgentOS Current Architecture & Reality

**Status date:** 2026-09-11  
**Canonical development authority:** `core/integration`  
**Observed integration head at this refresh:** `5093b59da5d45cdd016d606a7e2cb8abdb4cf22e`  
**Purpose:** concise evidence-bound map of implemented, verified, pending, research, and deprecated AgentOS Core architecture.

A source merge proves implementation, not live operation. A live receipt proves only the exact source generation, route, capability, executor and effect named by that receipt.

Control Inbox maintenance (#845) run 37260607129 on 2026-10-05 confirmed seven
non-assignment lines and stopped before auth, mutation, or restart. The helper
now bounds normalization to seven lines that systemd would independently ignore;
open assignment quote state and whole-file escape, control/separator, BOM, and
bare-CR guards reject ambiguous multiline syntax. Balanced quoted assignments and
quotes in independent ignored lines/comments remain harmless under systemd's
parser. Run 37279391137 stopped before mutation with seven ignored lines and one
quoted assignment; backslash/control/bare-CR counts were zero. The guard now
distinguishes balanced quoted assignments from physically open quote state.
Assignments, allowlist, and durable state remain preserved.
This source change still requires explicit maintenance deployment authorization.
Offline tests do not establish host configuration, Control Inbox recovery, Node
freshness, or Mio DM readiness. See
`docs/CONTROL_INBOX_SERVICE_REPAIR.md` for the deployment/receipt boundary.

## Canonical authority hierarchy

1. New explicit user intent and accepted governance constraints.
2. Canonical Project Identity and repository ownership.
3. ONE durable state: Canonical IR, active continuation pointer, Employee/assignment state, registries and dependency state.
4. Accepted Experience artifacts, scoped and provenance-bound.
5. Governed receipts/evidence from actual execution.
6. Client-local workspace/history/config and legacy status/pulse files.

Lower layers may inform higher layers but may not silently overwrite them.

## Current architecture / reality map

| Area | Current state | Evidence / boundary |
| --- | --- | --- |
| Core development authority | Canonical | `core/issue-* -> core/integration`; `main` is separate protected publication history, not active agent workspace |
| Realm / persistent control plane | Implemented, operating slices | exact live health must come from current runtime/Node receipts rather than a hard-coded generation |
| Node Registry / Node Map | Implemented | `agentos.node-registry/v0.1`, read-only `agentos.node-map/v0.1`; Node, surface, executor, backend and session identities remain separate |
| Runtime convergence | Implemented + bounded live acceptance | `node.runtime.converge` uses source-owned installers and exact accepted SHA; no caller-selected executable/argv/shell/path/service/env authority |
| Exact-generation source selection | Hardened | an authorized exact commit is fetched independently and must be an ancestor of the snapped allowlisted `core/integration` ref; runtime bytes come only from that exact commit. A concurrent merge advancing branch HEAD no longer invalidates an already authorized rollout (#320/#322) |
| Action Relay capability publication | Hardened | capability marker publication uses the fixed `agentos` group boundary, unique temp + fsync + atomic replace, explicit effective/parent GID checks, anchored runtime imports; marker presence is not execution authority |
| Canonical continuation IR | Implemented concrete slices | `agentos.ir/v1`, parent-fenced publication and active continuation selector; arbitrary hidden model state portability remains Research |
| Experience subsystem / Master Experience Floor | **Verified for bounded Oracle Codex #117 benchmark** | #117 closed completed 2026-09-11. ONE-dispatched A/B: baseline 6/7 -> hydrated 7/7; exact hydration manifest + per-dimension evidence; fixed 3-run B-minus-`core.branch-authority.v2` loses the only material improvement 3/3, attribution confidence `supported`; no regressed dimensions. Evidence: `.agentos/evidence/experience/oracle-issue117-one-dispatch-34565359787/` |
| Semantic Experience IR v1 | Candidate / broader work | bounded #117 verification does not automatically accept every semantic-v1 proposal or prove universal executor equivalence |
| General Cognitive IR | Research | do not rename successful continuation/Experience slices into portable arbitrary model-internal state |
| Agent Employee Runtime | Accepted foundation | durable Employee identity, assignments, leases, thread/state heads, role-scoped memory and receipts are organizational state |
| Persistent Supervisor/Reconciler | Implemented slices; operating acceptance continues | controller events reveal work but do not grant authority; no daemon-per-role architecture |
| Product Employees (#238) | Source/runtime hardening continues; live product markers still pending | wake receipt wait is bounded; missing receipt becomes `unknown` rather than infinite `queued`; product child launch requires exact governed S4 `awaiting_claim` evidence before dispatch and repeats the check before claim; Worker Host group transition occurs before no-new-privs. `ZEUS_WRITER_PERSISTENT_EMPLOYEE`, `YOUTUBE_AI_MANAGER_PERSISTENT_EMPLOYEE`, and product liveness markers remain unverified while #238 is open |
| Discussion Index (#290) | Candidate only | append-only ONE discussion provenance/search substrate is proposed in draft PR #293. It is not canonical authority, Canonical IR, Experience, or transcript-vault acceptance until integrated and live-accepted |
| Project/repository identity | Canonical explicit map | `docs/PROJECT_REPO_MAP.md`, `governance/product-migrations.json`; identity is never inferred from repository-name similarity |
| Evidence-first acceptance | Canonical | exact source/runtime identity + bounded sanitized terminal receipts; static CI cannot manufacture live VERIFIED markers |
| Governed content publishing (#686) | Implemented candidate / account migration not yet live-verified | `capability://content.publish` is a higher-level Content Artifact/batch/provider resolver composed over existing Core #154/#267 Social Runtime. Social bindings remain product-isolated: ZeusWriter/content.publish must use its own `content-publish` consumer and host-local Account Registry rather than borrowing Mio/Galaxy bindings. A bounded Ubuntu Action Relay bootstrap may migrate the pre-existing ZeusWriter Threads token into the shared vault without public posting or secret exposure. X API health is read-only probed; X web-assist remains unverified until a governed GUI provider/session proves readiness. |

## Node / capability semantics

Canonical identity layers are:

```text
Realm -> Node -> surface/extension -> executor adapter -> backend/model -> session/thread
```

Invariants:

```text
Node online != executor available
advertised != routable != authorized != successful
surface identity != backend/model identity
```

The Node Map is generated from ONE-side `NodeRegistry`, not manually maintained. Heartbeat freshness determines effective Node liveness. Executor liveness and terminal success require executor/provider evidence rather than inference from Node or extension presence.

Capability growth does not imply authority growth. Bounded capabilities remain typed and source-owned; no generic shell may be reconstructed by passing executable/module/argv/path/environment fields through a nominally typed action.

## Runtime identity and convergence

The retired fixed statement `live generation 6 / f842bee...` is historical evidence only.

Repository head is also not live-runtime truth. At this refresh `core/integration` is `5093b59da5d45cdd016d606a7e2cb8abdb4cf22e`, but every runtime acceptance must independently bind:

```text
repository + allowlisted source_ref + exact source_sha
runtime/worktree generation
service/capability profile
receipt id/timestamp
health/result
rollback/unknown state when applicable
credential_exposed=false where contracted
```

An exact rollout snapshots the allowlisted integration lane, separately fetches the requested immutable commit, proves that commit belongs to the lane by ancestry, and materializes only that commit. This prevents a moving `core/integration` HEAD from becoming an accidental global mutex for already-authorized deployments.

`source SHA matches` is still insufficient if required services, capability markers, permissions or runtime profile are absent/stale. Same-SHA convergence may therefore reconcile the fixed operating profile.

## Memory / IR boundaries

### Canonical continuation IR

`agentos.ir/v1` is bounded durable working state: goal, accepted decisions/constraints, task direction, lineage and evidence references. Publication is parent-fenced. Workspace selection, chat history and local configuration do not choose continuation authority.

### Experience

Experience is reusable accepted procedure/heuristic/failure knowledge, not another project-state store. Hydration identifies the exact accepted Experience items/digests without copying unrestricted bodies into receipts. New user intent always outranks hydrated Experience.

For #117 the bounded Oracle Codex Master Experience Floor is now Verified: baseline 6/7, hydrated 7/7, only `canonical_development_branch` improves, and withholding `core.branch-authority.v2` loses that improvement in all three fixed counterfactual repeats. This proves scoped value and attribution for that benchmark, not universal cross-model cognition.

### Employee state

Employee identity, assignment, lease, checkpoint/thread head, wake delivery, inbox/receipt and role-scoped memory are durable organizational state. Recent #238 decisions add two important failure semantics:

- a missing Employee wake receipt is not allowed to leave delivery `queued` forever; after the source-owned bounded wait it becomes `unknown` / `node_receipt_timeout`, and the same presence is not blindly redispatched;
- a product child is not launch-eligible until the exact Supervisor/S4 delivery already satisfies the governed `awaiting_claim` contract; the child repeats the same check immediately before claim.

These preserve at-most-once/TOCTOU safety instead of converting transient uncertainty into authority.

Legacy `STATUS.md`, Pulse, symlinked memory, old possession directives and chat history are migration evidence only.

## Project Identity / repository boundary

`agentmanager` owns Core/ONE/Realm/Node runtime, governance, receipts, canonical state and generic cross-repository capability contracts. Product UI/data/release intent/product CI/deployers/product-specific runtime behavior belong to their canonical repositories.

Character Blueprint remains identity-unresolved; `charactergenerator` was inspected and rejected as a provenance match. Model2IR has a real standalone v0.9.1 carrier lineage inside historical `agentmanager` branches, but no canonical standalone repository has yet been assigned; that lineage is migration provenance, not permission for new product/library development in Core.

An online environment is identified by environment + canonical repository + source ref + exact SHA/artifact + receipt, never branch name alone.

## Governance invariants

- `content.publish` provider resolution does not mint social write acceptance; #154/#267 exact product/platform/operation/account/write-intent acceptance still governs social effects.
- A Node or GUI executor being online does not make an X web publisher READY; provider/session/account health requires its own evidence.
- Capability does not imply authority.
- Event does not imply authority; events trigger reconciliation only.
- Transport failure does not widen authority or silently turn GitHub Actions into the steady-state control plane.
- Ambiguous privileged side effects remain `unknown`; do not blind-retry.
- Exact-generation deployment is immutable after authorization but still proves lane membership against the allowlisted integration ref.
- Parallel Core workers may advance `core/integration`; stale worker branches refresh/transplant rather than force-merge.
- Publication to `main` is separate explicit authority.
- Receipts are proof records, not intent or canonical state.

## Receipts / evidence

Receipts should be typed, bounded and sanitized enough to answer:

- Node/surface/executor/backend identity where trustworthy;
- canonical project and exact source generation;
- declared capability/job/action;
- routing, availability and authorization outcomes as separate fields;
- terminal result, timeout/`unknown` and rollback outcome;
- semantic digests/IDs rather than unrestricted bodies;
- credential boundary.

#117 additionally established a bounded attribution evidence pattern: hydration manifest + fixed per-dimension before/after projection + fixed counterfactual ablation, rather than raw provider output. Digest syntax follows the canonical hydration projection representation (raw lowercase 64-hex SHA-256 in that contract); do not invent parallel digest encodings.

A `VERIFIED` marker requires live evidence for the exact capability named. Static/source CI proves contracts/guards only.

## Deprecated / superseded paths

Historical or migration-only unless explicitly reactivated:

- `SHORT_TERM.md`, `LONG_TERM.md`, Pulse/status/brain-dump/manual `/report` as primary continuation authority;
- workspace-selected continuation or client config containing copied Canonical IR bodies;
- PR #119 prose-centric Experience v0 as a merge target; #117's accepted bounded implementation/evidence supersedes the old prose-only state;
- hard-coded runtime generation numbers as current truth;
- direct-to-`main` Core development and wholesale legacy proposal merges;
- moving-branch-HEAD equality as exact-generation deployment authority;
- generic deterministic temp filenames in shared Action Relay state;
- assuming account group membership means a long-lived process has the required effective group;
- infinite `queued` Employee wake state when terminal receipt is absent;
- launching product Employee children before exact governed S4 claim readiness;
- GitHub Actions as steady-state fallback for ONE transport failure;
- treating Node/surface/extension presence as executor success or backend identity;
- product-specific Oracle carriers in Core after an equivalent governed product-owned path and parity receipt exist.

## Canonical documentation ownership

Primary entry points: `README.md`, `ONBOARDING.md`, `AGENTS.md`, this file, `docs/AGENTOS_NODE.md`, `docs/CORE_BRANCH_MAP.md`, `docs/CORE_WORKER_MODEL.md`, and `docs/PROJECT_REPO_MAP.md`.

Architecture-sensitive accepted changes must update the relevant canonical entry point. Implementation/live evidence outranks stale prose. Historical claims belong in evidence/migration records, not current reality.

## Runner Window Realm Node inspection

Runner Window now has explicit bounded public intents for Realm Node health and interactive desktop reachability:

- `node.realm inspect node_id=<id>` reads the canonical NodeRegistry projection and returns only bounded non-secret status markers such as heartbeat age, effective status, platform, role, capability count and whether the node advertises `desktop.session.inspect`.
- `node.desktop probe node_id=<id>` is an active liveness check. It requires the node to be currently online and to advertise `desktop.session.inspect`, then queues that fixed task through RealmFabric and waits for a bounded receipt. The result is classified as `READY`, `NOT_INTERACTIVE`, `OFFLINE`, `CAPABILITY_MISSING`, `NOT_REGISTERED`, `TIMEOUT`, or `ERROR`.

Callers no longer need to target an Oracle runner merely to inspect an enrolled Windows node. They submit the public intent to Runner Window, which routes the fixed control action through the canonical Core control lane. Raw node tokens, task payload flexibility, screenshot bytes and arbitrary shell execution are not exposed through these intents.

## Google Flow / Google Vids live generation through Runner Window

Google Flow and Google Vids now have bounded Runner Window generation intents backed by the Oracle persistent Chromium GUI profile:

- `media.google-flow generate`
- `media.google-vids generate`

Both accept only a bounded UTF-8 prompt and route to the GUI scheduler lane with the shared `oracle-gui-profile` mutex plus provider-specific locks. The implementation uses the existing persistent browser profile over CDP and never exposes Google credentials through the public dispatch contract.

Generation receipts expose only bounded status markers plus durable artifact metadata when a clip can be downloaded. Provider-specific UI drift is reported as a classified state such as `AUTH_REQUIRED`, `UI_UNRECOGNIZED`, `GENERATION_FAILED`, `TIMEOUT`, or `GENERATED_NOT_DOWNLOADED` rather than being misreported as success.

The live acceptance workflow uses the same prompt for Flow and Vids so output quality, latency and provider behavior can be compared on equivalent input. Generated files are kept under `/home/ubuntu/agent-data/artifacts/google-flow/` and `/home/ubuntu/agent-data/artifacts/google-vids/` when download succeeds.

## Vision Studio MVP orchestration

Vision Studio now has a bounded public production intent:

- `media.vision-studio produce project_id=<id>`

The initial source-owned production `rain-exit-v001` composes the existing Google Flow GUI generator rather than inventing a parallel video transport. The Oracle-side producer runs fixed shot prompts, collects only successful downloaded clip paths, normalizes/trims the accepted clips into a 10-second 9:16/24fps MP4 with ffmpeg, adds a low-level synthetic rain ambience bed for the MVP, and emits a bounded production receipt with per-shot generator evidence and final artifact metadata.

The public caller cannot pass shell, executable, provider credentials, filesystem paths, arbitrary ffmpeg arguments, or arbitrary story text through this intent; it supplies only a validated project ID. New productions must be source-defined and reviewed before they become routable. This is an MVP orchestration slice, not proof of general autonomous filmmaking quality or multi-provider routing.

## Runner Window GUI worker repair

Oracle GUI Worker installation/repair is exposed as the bounded public intent `browser.gui install`. Automatic repair carriers must use the hosted reusable AgentOS dispatch path rather than adding a push-triggered direct-Oracle workflow. The existing direct Oracle installer remains manual-only as a break-glass/legacy surface.

The governed path is:

`hosted carrier -> Runner Window -> maintenance scheduler lane -> agentos.gui_worker.install -> persistent Chromium/CDP + display/VNC services`

The bounded command file `.agentos/commands/oracle-gui-worker-install.json` may trigger the hosted repair carrier. This keeps runner selection and Oracle execution authority inside Runner Window while preserving the existing installer implementation.

