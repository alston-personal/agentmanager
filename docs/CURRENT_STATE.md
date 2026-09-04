# AgentOS Current Architecture & Reality

**Status date:** 2026-09-04  
**Canonical development authority:** `core/integration`  
**Purpose:** one concise reality map for implemented, verified, pending, research, and retired AgentOS Core architecture.

This document is intentionally evidence-bound. A source merge proves implementation, not live operation. A live receipt proves only the exact generation, route, capability, executor, and effect that the receipt attests.

## Product goal

AgentOS should let a user change conversation, model, executor, extension, Node, or machine without reconstructing the project from conversation history. Durable project state, accepted experience, authority, execution state, and evidence live outside model-local context. Models and IDE extensions are replaceable execution surfaces.

## Canonical authority hierarchy

1. New explicit user intent and accepted governance constraints.
2. Canonical Project Identity and repository ownership.
3. ONE durable state: Canonical IR, active continuation pointer, Employee/assignment state, registries, dependency state.
4. Accepted Experience IR, scoped and provenance-bound.
5. Governed receipts/evidence from actual execution.
6. Client-local workspace/history/config and legacy pulse/status files.

Lower layers may inform higher layers but may not silently overwrite them.

## Reality map

| Capability | Current state | Canonical implementation / evidence boundary |
| --- | --- | --- |
| Persistent control plane and Realm | Implemented and operating slices | `agent_core/control_plane.py`, Realm services/registry, exact live state must be read from runtime/Node receipts rather than a hard-coded historical generation |
| Node Registry / Node Map | Implemented + tested | `agent_core/node_registry.py`; `agentos.node-registry/v0.1` and read-only `agentos.node-map/v0.1` |
| Node heartbeat freshness | Implemented | reported `online` becomes effective `offline` when heartbeat is stale; current default stale floor is 30s with a minimum of 15s |
| Node/runtime provenance and drift | Implemented | Node Map projects runtime convergence/drift/unknown; source equality alone is not operating-profile equality |
| Bounded Oracle runtime convergence | Implemented + live accepted under #242 | typed `node.runtime.converge`, fixed source-owned installers, exact `core/integration` SHA, no caller shell/argv/path/service authority, rollback + sanitized receipts; #242 completed 2026-09-04 |
| Action Relay generation reconciliation | Implemented | Core maintenance can reconcile an old immutable Action Relay runtime to current accepted Core generation without caller-supplied execution fields |
| Node vs executor identity | Canonical invariant; broader extraction/acceptance still tracked by #152 | Node is durable Realm participant; executor/surface/backend/session are distinct identities; `Node online != executor available` |
| Executor status semantics | Canonical invariant | `advertised != routable != authorized != successful`; do not collapse these into one capability flag |
| ChatGPT Web → ONE | Bootstrap path implemented | authority-driven routing prefers direct ONE/MCP/App; current ChatGPT bootstrap may use Control Inbox #50; GitHub Actions is not a generic failure fallback |
| Bounded executor jobs through ONE | Implemented slices | declarative fixed job types route through ONE → bounded Action Relay → sanitized durable receipt; no generic remote shell |
| Canonical continuation IR | Implemented + verified concrete cross-extension slices | `agentos.ir/v1`, parent-fenced publication, active continuation selector; Gemini/Codex continuity has concrete accepted evidence, but arbitrary portability remains unproven |
| Active continuation selector | Implemented | pointer stores project/index/IR identity only; it is not another state store and must fail closed on stale references |
| Experience subsystem v0 prose design | Deprecated | PR #119 direction is superseded; do not merge wholesale |
| Semantic Experience IR v1 | Active candidate under #117 | current focused design is `agentos.experience/v1` carrying `agentos.experience-ir/v1`, typed semantic nodes, stable digests, extraction validation, ONE-owned Experience Set, semantic hydration receipts; PR #229 remains unmerged as of this snapshot |
| Master Experience Floor | Strong live evidence, issue still open | observed governed A/B reached baseline 6/7 → prehydrated 7/7; ceiling-aware criterion is the current candidate logic, but #117 remains open and canonical Experience IR integration/ablation evidence is not yet fully accepted |
| General Cognitive IR across arbitrary models | Research | Canonical continuation IR and Experience IR are bounded concrete forms; do not claim portable hidden activations or arbitrary executor equivalence |
| Agent Employee Runtime | Accepted foundation | durable Employee identity is distinct from executor/session/Node; durable assignments, leases, state/thread heads, scoped memory and receipts are canonical operating state |
| Persistent Supervisor/Reconciler | Implemented/operating acceptance work | Supervisor is Core controller process, not an Employee; events reveal candidate work but do not grant authority; no daemon-per-role architecture |
| Product Employees (Zeus Writer / YouTube AI Manager) | Source/runtime profile implemented; live production acceptance remains open under #238 | fixed Employee contracts, wake-only Node profile and shared Worker Host are source-controlled; real persistent writing/scan continuity and liveness markers still require operating evidence |
| Project/repository identity | Canonical and explicit | `docs/PROJECT_REPO_MAP.md`, `governance/product-migrations.json`; project identity is never inferred solely from a repository name |
| Parallel Core workers | Accepted | canonical Core thread is authority/control-plane; issue workers execute independently; dependencies block exact steps, not whole projects |
| Evidence-first acceptance | Canonical | `.agentos/evidence/`, sanitized receipts, exact source/runtime identity; static CI cannot manufacture live VERIFIED markers |
| Protected publication authority | Canonical | `core/issue-* -> core/integration`; publication to protected `main` is separate explicit authority and is never implied by `continue`, CI green, mergeability, capability availability, or worker completion |

## Current Node Map semantics

The canonical map is generated from ONE-side `NodeRegistry`; it is not a manually maintained list. `agentos.node-map/v0.1` includes:

- Realm id, Node count and effective online count;
- each Node's role (`core` or `client`), hostname/platform, capabilities and tool presence;
- `surface_inventory` for provider/IDE surfaces without pretending the surface equals a backend model;
- heartbeat age and stale reason;
- runtime provenance / converged, drifted, or unknown state;
- workspace-root policy projection for legal execution placement;
- Realm-level aggregate capabilities, tools, and surface providers.

Known real identities include Oracle/Core (`oracle-core-node`) and the Windows client `vopc5750`, but documentation must not hard-code them as the complete live Realm. Live membership and capabilities must come from Node Map / receipts.

Executor inventory is a child layer, not part of Node liveness. A Gemini, Codex, Claude-extension, desktop host, local backend, or Employee Worker Host can become unavailable while its host Node remains online.

## Runtime source and deployment identity

The old fixed statement `live generation 6 / f842bee...` is retired. It was valid historical evidence, not a permanent runtime identity.

Canonical source development currently advances on `core/integration`; at this documentation refresh its observed head is `0c47fe2a0c325898814f4bea7c1e009359983477`. That value is a repository snapshot, not a claim that every live process is already on that SHA.

Every live acceptance must instead bind:

```text
repository + source_ref + exact source_sha
runtime/worktree generation
service/capability profile
receipt timestamp/id
health/result
rollback state when mutation occurred
credential_exposed=false where applicable
```

`source SHA matches` is insufficient if required services/capability markers are absent or stale. Current `node.runtime.converge` therefore reconciles the fixed operating profile even when the checkout is already at the requested generation.

## Memory and IR boundaries

### Canonical continuation IR

`agentos.ir/v1` represents bounded durable working state: goal, accepted decisions/constraints, task direction, lineage and evidence references. Publication is parent-fenced. Workspace or client-local history cannot choose continuation authority.

### Experience IR

Experience is reusable learned procedure/heuristic/failure knowledge, not another project-state store. Current #117 direction uses semantic Experience IR with provenance, scope, digest, expected behavior dimensions and extraction/acceptance fences. Human summaries are presentation only and must not define semantic identity.

A hydration receipt identifies the exact accepted Experience items/digests used without copying their bodies into the receipt. New user intent outranks hydrated Experience.

### General Cognitive IR

Still Research. Do not rename successful continuation or Experience slices into a claim that arbitrary model internal state is portable.

### Employee memory/state

Employee identity, assignment, lease, checkpoint/thread head, inbox/receipt and role-scoped memory are durable organizational state. Legacy `STATUS.md`, Pulse files, symlinked memory, old possession directives, and chat history can be migration evidence only; they are not current authority.

## Project Identity / repository boundary

`agentmanager` owns Core/ONE/Realm/Node runtime, governance, receipts, canonical state and generic cross-repository capability contracts. Product UI, data, release intent, product CI/deployers and product-specific runtime logic belong to canonical product repositories.

Current canonical map and unresolved identities are maintained in `docs/PROJECT_REPO_MAP.md`. Important unresolved boundaries include Character Blueprint and Model2IR repository assignment; historical Model2IR branches in `agentmanager` are migration provenance, not permission for continued product/library development in Core.

An online environment is not defined by branch name. Deployment identity is environment + canonical repository + source ref + exact SHA/artifact + receipt.

## Governance invariants

- **Capability does not imply authority.** Presence of a tool/capability/runner does not authorize its use.
- **Event does not imply authority.** Issue updates, timers, webhooks, messages, receipts and dependency changes trigger reconciliation only.
- **Transport failure does not widen authority.** ONE failure never silently falls back to GitHub Actions for control-plane intents.
- **No generic shell by reconstruction.** Bounded actions/jobs cannot accept executable, argv, shell, module, arbitrary path/service/environment or credentials merely for convenience.
- **Ambiguous external effects remain `unknown`.** Do not blind-retry privileged side effects after timeout/crash.
- **Capability growth requires governance growth.** Stronger mutation surfaces require tighter schemas, receipts, rollback, observability and non-authority statements.
- **Core authority != Core serialization.** Independent worker lanes run concurrently; only declared dependency edges block exact steps.
- **Publication is separate.** `main` remains accepted/publication state and is not an active agent workspace.

## Receipts and evidence

Receipts are proof records, not state or intent. They should be typed, bounded, sanitized and exact enough to answer:

- who/what acted (Node, surface, executor adapter, backend identity when trustworthy);
- what canonical project/source generation was used;
- what declared capability/job/action was authorized;
- whether routing, authorization and executor availability succeeded;
- terminal result, timeout/unknown classification and rollback outcome;
- relevant semantic digests rather than secret/raw bodies;
- credential boundary (`credential_exposed=false` where that contract applies).

A `VERIFIED` marker requires live evidence for the capability it names. Static/source CI may prove contracts and guards, but may not assert live service/product liveness.

## Deprecated / superseded paths

Treat these as historical or migration-only unless a current canonical document explicitly reactivates them:

- `SHORT_TERM.md` / `LONG_TERM.md`, pulse-only memory, brain dumps and manual `/report` as primary continuation authority;
- workspace-selected continuation;
- client-specific config files containing copied Canonical IR bodies;
- PR #119 prose-centric Experience v0 direction;
- legacy direct-to-`main` Core proposal branches; extract still-needed deltas onto current `core/issue-*` branches rather than merging wholesale;
- legacy Bootstrap auto-push / evidence-push path; current bootstrap is explicit and exact-generation, not steady-state control plane;
- `node.runtime.converge -> shell.exec` / embedded script carrier; current converge is a fixed typed semantic action;
- hard-coded historical runtime generation numbers as current truth;
- treating Node OS/platform or Node online status as proof an executor is available;
- treating Anthropic/Codex/Gemini extension brand as proof of actual backend model identity;
- product-specific Oracle carriers inside Core after an equivalent governed product-owned path and parity receipt exist.

## Canonical documentation ownership

Primary entry points are `README.md`, `ONBOARDING.md`, `AGENTS.md`, this file, `docs/AGENTOS_NODE.md`, `docs/CORE_BRANCH_MAP.md`, `docs/CORE_WORKER_MODEL.md`, and `docs/PROJECT_REPO_MAP.md`.

Architecture-sensitive changes must update the relevant canonical entry point in the same accepted change set. When implementation or live evidence contradicts prose, the prose must be corrected; historical claims belong in evidence/migration documents rather than being preserved as current reality.
