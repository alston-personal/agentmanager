# AgentOS Core Control Room

**Status date:** 2026-08-28  
**Purpose:** canonical development-thread map for AgentOS Core. This file captures current synthesis, live runtime boundaries, Node Map/capability state, Project Identity, memory/IR, governance, receipts/evidence, deprecated paths, and next architectural work.

> Implementation truth belongs to executable code/tests/evidence plus `docs/CURRENT_STATE.md`. When this file conflicts with verified runtime evidence, evidence wins and this file must be corrected.

## 1. Documentation discipline

- AgentOS Core architecture and implementation discussion has one canonical development thread.
- Important decisions must be persisted to repository documentation; chat is not a source of truth.
- `docs/CURRENT_STATE.md` = authoritative implementation/research reality map.
- `docs/CORE_CONTROL_ROOM.md` = development synthesis, active boundaries, Node Map view, and next work.
- `docs/CORE_DEPLOYMENT_AUTHORITY.md` = canonical live Core generation/lease contract.
- `docs/AGENTOS_NODE.md` = node-local discovery/capability contract.
- Architecture-sensitive changes remain subject to Documentation Reality Guard.
- Prefer consolidation and retirement over creating parallel architecture narratives.

## 2. Realm / Node Map

### Verified architecture

`agent_core/node_registry.py` implements a persistent ONE-side Realm Node Map with node manifests, capabilities, tool presence, surface inventory, heartbeat freshness, online/offline derivation, and Realm-level capability aggregation.

### Node truth rules

- Conceptual/logical surfaces are not automatically live Realm nodes.
- A node becomes operationally real only through enrollment/registry state and fresh runtime evidence.
- Capability advertisement is descriptive, not an authority grant.
- Transport reachability, ControllerService reachability, node capability availability, and mutation authority are four separate states.
- The authoritative node count/status comes from live NodeRegistry state, never from a diagram or conversation assumption.

### Current evidenced roles

| Node / surface | Classification | Current interpretation |
|---|---|---|
| `oracle-core-node` | Core runtime node | Verified Core/ONE participant and canonical Core source/runtime authority node |
| ChatGPT Web logical node | Cognitive/user surface | Architectural client surface; do not call it an enrolled live Realm node without registry + heartbeat evidence |
| User PC / thin node | Candidate/edge node | Must be proven through node enrollment, capability advertisement, heartbeat provenance, and readiness evidence |
| `vopc5750` | Node Golden Path target | Core dispatch now reaches ControllerService; `agent.surface.inspect` capability convergence remains a Node responsibility when not advertised |

### Node Map target fields

- `node_id`, role, platform/hostname
- reported/effective status and heartbeat age/provenance
- capabilities
- tool presence
- surface inventory/providers
- authority/trust constraints
- optional benchmark/cost/latency metadata
- runtime/version provenance where needed for convergence debugging

## 3. Capability model

AgentOS must keep these questions distinct:

```text
Does the node advertise the capability?
Can ONE route to the node?
Does policy/authority allow the effect?
Did execution actually succeed?
```

A missing advertised capability should produce a node/capability outcome, not masquerade as a Core route failure. Issue #64 proved this distinction: the final real-path probe reached ControllerService and returned a node-level `NODE_CAPABILITY_NOT_ADVERTISED` outcome instead of the previous Core HTTP 404.

Repeated successful high-level reasoning may become a candidate skill/reflex, but capability promotion requires tests, provenance, failure boundaries, authority constraints, and rollback. Capability growth must never silently widen authority.

## 4. Canonical Project Identity

The earlier claim that canonical Project Identity was unproven is now stale.

AgentOS now has an explicit canonical project registration contract in `agent_core/project_store.py` using:

```text
agentos.project/v1
```

Core invariants:

- `project_id` is a stable logical identity.
- project identity is independent from repository name, branch, checkout path, runtime path, deployment target, and state storage.
- aliases are explicit project metadata, not alternate authorities.
- source authority is explicit: `repo`, `branch`, `canonical_path`, `node`.
- canonical project state location is explicit.
- compatibility fields are projections for older readers, not independent authority.
- registration projects identity into Governance Directory as `project://<project_id>`.
- canonical resolution must fail closed for mutation when source/integrity requirements are incomplete.

`agentos-core` has governed registration/evidence and tests proving identity/repository/checkout separation.

### Project continuation rule

The normal path for `continue <project>` must be:

```text
user / cognitive surface
  -> ONE
  -> AgentOS resolver
  -> canonical Project Identity
  -> state / continuation / capability / execution-head resolution
  -> continuation envelope
```

GitHub/source scanning remains valid for debugging and implementation work, but is not the normal project-identity discovery mechanism.

## 5. ChatGPT Web -> ONE -> AgentOS canonical query path

A cross-chat failure previously exposed an architectural error: a conversation tried to reconstruct AgentOS/project state by searching source code. That is not the intended control-plane path.

Architectural invariant:

> **Use AgentOS; do not rediscover AgentOS from its source code.**

The cognitive surface should depend on a replaceable AgentOS resolve interface, conceptually:

```text
agentos.resolve(user_intent)
```

returning a canonical envelope with project identity, active goal, execution head, relevant capabilities/authority, evidence pointers, and next action.

Project Identity is now materially stronger than when this requirement was first written, but the strongest cross-device/new-chat acceptance remains a separate end-to-end closure test.

## 6. Memory, continuation state, and Cognitive IR

Historical three-layer memory remains conceptually useful:

- **L1 — immediate / working:** active task, execution state, reconstructable local context.
- **L2 — project / continuation:** decisions, project facts, unresolved questions, frontier, next direction.
- **L3 — long-term / cross-project:** stable knowledge, preferences, reusable patterns, lessons.

Current AgentOS is broader than the old `SHORT_TERM.md` / `LONG_TERM.md` memory model. Canonical project state, continuation/work state, governance state, runtime state, receipts/evidence, and validated knowledge are separate concerns.

### IR boundary

`IR = Intermediate Representation`.

An operational `agentos.ir/v1`-shaped handoff envelope may exist and be useful. That is not the same claim as a generally sufficient model-independent Cognitive IR for arbitrary model/executor switching.

Preferred relationship:

```text
L1/L2/L3 + canonical/project/work state
       -> retrieve / reconcile / compile
       -> continuation IR
       -> Context Adapter / executor
       -> execution + receipts
       -> validated consolidation back to state/memory
```

Cognitive IR remains **Research** until a repeatable cross-model benchmark proves preservation of active goal, constraints/decisions, rejected paths, open questions, and next direction.

IR is not a fourth memory layer and must not become a competing source of truth.

## 7. Governance model

Core governance now needs to be read as several orthogonal authorities rather than one generic permission flag:

- responsibility/provider authority — Governance Directory;
- project/source/state authority — canonical Project Identity + Governance projection;
- protected-branch authority — explicit branch governance;
- runtime deployment authority — Core deployment generation/lease state;
- node capability advertisement — NodeRegistry;
- effect/execution authorization — capability-specific governance/policy;
- evidence acceptance — receipts/tests/live path proof.

Core rule:

> **Capability does not imply authority. Identity does not imply lifecycle ownership. Passing CI does not imply live mutation authority.**

This is especially important for Core deployment: logical equality of `lease_owner` no longer permits generation advance while a lease is active.

## 8. Core runtime / deployment status

Realm Fabric is a single live Core service governed by:

```text
/home/ubuntu/agent-data/governance/core-deployment.json
```

Current deployment model:

```text
claim next generation
  -> install exact claimed release
  -> attest observed release
  -> converge
  -> release / expire ownership before another generation advance
```

The installer does not own generation transition.

An active lease blocks generation advance even for the same owner. This closes the delayed-workflow/same-owner race discovered during the 2026-08-28 Node Golden Path incident.

For exact contract details see `docs/CORE_DEPLOYMENT_AUTHORITY.md`.

### Issue #64 closure boundary

The final real transport acceptance proved:

```text
Bootstrap Control Inbox
  -> Oracle bridge / ONE
  -> POST /v1/controller/dispatch
  -> ControllerService
```

Core-level HTTP 404 was eliminated. Final outcome moved to the expected Node layer (`NODE_CAPABILITY_NOT_ADVERTISED` for `agent.surface.inspect`). Evidence is persisted in:

```text
.agentos/evidence/issue-64/control-inbox.json
```

Therefore Node work must not reopen the Core route incident unless fresh evidence shows regression.

## 9. Receipts and evidence

Receipts are first-class architecture artifacts, not incidental logs.

Evidence levels should be interpreted carefully:

1. code exists;
2. unit/contract test passes;
3. governed workflow completes;
4. runtime state attests intended generation/process;
5. real transport path reaches intended subsystem;
6. target capability executes and produces expected outcome.

A lower layer must not be described as proof of a higher layer.

Examples:

- `/health` proves liveness, not correct controller dispatch;
- process PID proves a process exists, not that the expected release is deployed;
- a workflow success proves its steps passed, not necessarily that a downstream node capability exists;
- `NODE_CAPABILITY_NOT_ADVERTISED` after ControllerService entry is valid Core-route evidence but not Node readiness evidence.

Architecture-sensitive acceptance should preserve receipts/evidence under `.agentos/evidence/` when practical.

## 10. Brain / event-trigger architecture

AgentOS architectural cognition must not equal a permanently open ChatGPT Web session.

Target loop:

```text
node/event source
  -> event envelope
  -> Trigger Registry / Attention Gate
  -> L1 reflex / deterministic handling
  -> L2 bounded deliberation / policy
  -> L3 cognition when necessary
  -> ONE capability/executor resolution
  -> governed action
  -> receipt/evidence
  -> canonical-state / memory consolidation
```

Core principle:

> **Reflex first, cognition when necessary.**

Successful recurring cognitive solutions may be compiled downward into governed capabilities/reflexes only after evidence and generalization tests.

## 11. Core Console / Observatory

A Core website remains desirable as a **read-only Console / Observatory** first, not as another source of truth.

MVP views:

1. Realm Node Map + capabilities/status/provenance
2. Project/Governance/Resource registries
3. Canonical docs + decision index
4. Roles, executors, services and ownership
5. Tasks, receipts and evidence
6. Memory / continuation / IR observability
7. Core deployment generation/lease state
8. Governance state and warnings

Do not make embedding ChatGPT Web a Core dependency. The Console consumes canonical read APIs; it does not become the brain or authority store.

## 12. Deprecated / historical paths

Do not present these as current canonical architecture:

- `SHORT_TERM.md` / `LONG_TERM.md` as the complete memory system;
- pulse files / brain dumps as canonical state;
- manual `/report` as the sole continuity mechanism;
- repository or checkout path as Project Identity;
- GitHub/source rediscovery as the normal `continue <project>` path;
- conceptual nodes counted as live NodeRegistry entries;
- capability advertisement interpreted as execution authority;
- process PID or `/health` alone as Core acceptance;
- installer-side implicit deployment-generation advance;
- same-owner active-lease generation advance;
- legacy unfenced Core deploy calls;
- runtime-generation systemd drop-ins treated as canonical authority when deployment state exists;
- Wiki/Memory Palace treated as independent canonical stores without verified implementation/authority semantics.

Compatibility readers/adapters may remain temporarily but must not become parallel authorities.

## 13. Immediate Core priorities

1. Finish and repeatedly prove the new-chat / cross-device `ChatGPT Web -> ONE -> AgentOS resolve` path using canonical Project Identity rather than source rediscovery.
2. Publish live NodeRegistry output as the authoritative Realm Node Map and clearly distinguish enrolled nodes from logical surfaces.
3. Complete Node capability/heartbeat/runtime convergence for Golden Path nodes without conflating node failures with Core routing failures.
4. Extend canonical project registration/resolution to projects beyond `agentos-core`, preserving stable project IDs and explicit source authority.
5. Reconcile operational continuation envelopes with research-level Cognitive IR and design a repeatable cross-model benchmark.
6. Map L1/L2/L3 memory concepts to concrete current State/Cognition/Work stores and remove remaining ambiguous legacy-memory claims.
7. Strengthen receipt/evidence indexing so Console/agents can answer “what is proven, by which path, at which generation?” without scanning workflows manually.
8. Design Event/Trigger/Attention Fabric and cognition-to-reflex promotion with explicit governance thresholds.
9. Build the read-only Core Console only over authoritative registries/APIs.

## 14. Anti-drift questions

Before implementing a new Core mechanism, ask:

1. Does an existing registry/state/manager already own this responsibility?
2. Is the problem missing data/population/resolution rather than missing architecture?
3. Is the proposed mechanism Core, research, compatibility, or application-specific?
4. Which authority is being exercised: identity, capability, effect, branch, deployment generation, or evidence acceptance?
5. What executable/live evidence will prove the intended layer?
6. Which canonical document must change with the implementation?
7. Am I using AgentOS through its control plane, or bypassing it and reconstructing truth from source/memory?
8. Am I accidentally promoting compatibility metadata into a second source of truth?
