# AgentOS Current Architecture & Reality

**Status date:** 2026-09-11  
**Canonical development authority:** `core/integration`  
**Observed integration head at this refresh:** `5093b59da5d45cdd016d606a7e2cb8abdb4cf22e`  
**Purpose:** concise evidence-bound map of implemented, verified, pending, research, and deprecated AgentOS Core architecture.

A source merge proves implementation, not live operation. A live receipt proves only the exact source generation, route, capability, executor and effect named by that receipt.

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
