# AgentOS Core Control Room

**Status date:** 2026-08-28  
**Purpose:** canonical development-thread map for AgentOS Core. This file captures current synthesis, open architectural questions, Realm/Node observations, and decisions that should not remain trapped in chat history.

> Implementation truth still belongs to `docs/CURRENT_STATE.md` plus executable code/tests/evidence. When this file conflicts with implementation evidence, evidence wins and this file must be corrected.

## 1. Documentation discipline

- AgentOS Core architecture and implementation discussion has one canonical development thread.
- Important decisions must be persisted to repository documentation; chat is not a source of truth.
- `docs/CURRENT_STATE.md` = authoritative implementation/research reality map.
- `docs/CORE_CONTROL_ROOM.md` = current development synthesis, active questions, Node Map view, and next architectural work.
- Architecture-sensitive changes should continue to be covered by Documentation Reality Guard.
- Periodically consolidate, deduplicate, and retire stale documentation rather than creating parallel narratives.

## 2. Realm / Node Map

### Verified architecture

`agent_core/node_registry.py` implements a persistent ONE-side Realm Node Map with node manifests, capabilities, tool presence, surface inventory, heartbeat freshness, online/offline derivation, and Realm-level capability aggregation.

### Currently evidenced nodes

| Node | Classification | Evidence status | Known / expected capabilities |
|---|---|---|---|
| `oracle-core-node` | Core runtime node | **Observed/verified in recent continuation execution** | AgentOS Core runtime, allowlisted Core task execution, control-plane participation |
| ChatGPT Web logical node | Intended cognitive/browser node | **Not yet verified as an enrolled/heartbeat node** | Interactive cognition, user-facing conversation; future bridge/surface capabilities |
| User PC | Candidate client node | **Not yet proven here as a distinct current Realm registry entry** | Local tools/runtime depending on installed client/bridge |

**Important:** Do not count conceptual/logical nodes as live Realm nodes. The authoritative runtime count must come from the live `AGENT_DATA_ROOT/realm/nodes.json` / `NodeRegistry.node_map()` output, not conversation assumptions.

### Node Map target fields

- `node_id`, role, platform/hostname
- reported/effective status and heartbeat age
- capabilities
- tool presence
- surface inventory/providers
- authority/trust constraints (to be integrated from governance)
- optional benchmark/cost/latency metadata

## 3. AgentOS Core Console / website

A Core website is desirable, but should start as a **read-only Console / Observatory**, not as a replacement for all development surfaces.

MVP views:

1. Realm Node Map + capabilities/status
2. Project/Governance/Resource registries
3. Canonical docs + ADR/decision index
4. Roles, executors, services and ownership
5. Tasks, receipts and evidence
6. Memory / continuation / IR observability
7. Governance state and warnings

Do not make embedding ChatGPT Web itself a Core dependency. ChatGPT/GPT web experiences are product surfaces; the Core Console should use a replaceable cognitive-executor interface. A first-party/API-backed chat surface can be added later without making one browser tab the system brain.

## 4. Brain / event-trigger architecture

Current interactive cognition is heavily driven by ChatGPT sessions, but the AgentOS architectural brain must not equal ChatGPT Web.

Target loop:

```text
node/event source
    -> event envelope
    -> Trigger Registry / Attention Gate
    -> governance/policy
    -> ONE capability/executor resolution
    -> cognitive executor
    -> plan/action
    -> node capability execution
    -> receipt/evidence
    -> canonical-state / memory consolidation
```

This is the missing bridge from a passive chat-driven system toward the "everything can have a brain" goal. Nodes should publish events; policy decides which events deserve cognition and which executor should handle them. The system must not depend on keeping a ChatGPT browser tab awake as a daemon.

Potential event classes: heartbeat/state changes, filesystem/repo changes, task completion/failure, browser/UI events, external webhooks/connectors, scheduled events, device/sensor signals, and explicit user messages. Every action remains subject to capability and authority rules.

## 5. Project Identity / Registry status

AgentOS **does already have registry infrastructure capable of representing projects**:

- `GovernanceDirectory.VALID_KINDS` includes `project`.
- Governance Directory provides identity, ownership/provides, implementation, authority, lifecycle state and metadata.
- Resource Registry separately tracks registered world/resources and their observed/verification state.

However, as of this review, no evidence has yet been found that a **canonical Project Identity contract** with stable `project_id` + aliases + repo/workspace/service/product mapping is consistently populated and used by every project resolver.

Therefore the current problem should be framed as:

> registry primitives exist; canonical project-identity population/resolution is not yet proven end-to-end.

This distinction must be tested before adding another registry.

## 6. Three-layer memory and IR

Historical three-layer memory model remains conceptually useful:

- **L1 — immediate / working memory:** active task, active context, execution state, short-lived reconstructable data.
- **L2 — project / mid-term memory:** project state, decisions, facts, unresolved questions, frontier and continuation knowledge.
- **L3 — long-term / cross-project memory:** stable knowledge, preferences, lessons, reusable patterns and domain knowledge.

Current AgentOS has evolved beyond an early `SHORT_TERM.md` / `LONG_TERM.md` memory-only model. Production/research documentation now separates canonical project state, cognitive state, work/deferred state, governance state and execution evidence.

**IR = Intermediate Representation.** In AgentOS, Cognitive IR means a model-independent portable representation of the current working position for continuation across models/executors.

IR should **not** become a fourth memory layer and should not replace memory. Preferred relationship:

```text
L1/L2/L3 + canonical/project/work state
       -> retrieve / reconcile / compile
       -> Cognitive IR / continuation package
       -> Context Adapter / executor
       -> execution + receipts
       -> validated consolidation back to state/memory
```

The repo currently marks model-independent Cognitive IR as **Research**, while recent continuity data already uses an `agentos.ir/v1` continuation envelope operationally. These must be distinguished: an operational IR-shaped handoff schema exists; the stronger claim of generally sufficient cross-model Cognitive IR is not yet proven.

## 7. LLM Wiki / Memory Palace

Current evidence does not support treating either as a finished standalone Core subsystem.

- Earlier design discussions contained a `knowledge/` concept described as Wiki-like persistent knowledge.
- No verified current implementation named `LLM Wiki` or `Memory Palace` has been established in this review.
- They should therefore be treated as **knowledge/navigation concepts**, not as separate sources of canonical truth.

If retained, their proper relationship is:

```text
Canonical state / validated memory
      -> human/LLM-readable knowledge projection (Wiki)
      -> associative/navigation/index layer (Memory Palace)
      -> retrieval
      -> IR compilation
```

The Wiki/Palace should never silently overwrite canonical state. Promotion back into durable memory/state requires validation/provenance.

## 8. Immediate Core priorities exposed by this review

1. Query the **live** NodeRegistry and publish its output as the authoritative Realm Node Map.
2. Verify whether PC and ChatGPT Web are actually enrolled nodes versus conceptual surfaces.
3. Audit Governance Directory `kind=project` entries and project resolver behavior before creating any new Project Registry.
4. Reconcile the operational `agentos.ir/v1` continuation envelope with the research-level Cognitive IR definition.
5. Audit L1/L2/L3 memory code/data paths and explicitly map them to current State/Cognition/Work architecture.
6. Decide whether Wiki/Memory Palace remain named subsystems or become projections/indexes over the memory/state system.
7. Add Event/Trigger Fabric design (Trigger Registry + Attention Gate) before attempting autonomous node cognition.
8. Build Core Console only after the underlying registry/read APIs are authoritative; start read-only.

## 9. Anti-drift rule

Before implementing a new Core mechanism, ask:

1. Does an existing registry/state/manager already own this responsibility?
2. Is the problem missing data/population/resolution rather than missing architecture?
3. Is the proposed mechanism Core, research, or an application-specific consumer?
4. What executable evidence will prove it works?
5. Which canonical document must change with the implementation?
