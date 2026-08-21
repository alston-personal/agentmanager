# AgentOS State Kernel v2

Status: design baseline for `feature/state-kernel-v2`.

This document intentionally narrows AgentOS. The goal is not to replace MCP, ACP, A2A, agent memory products, browser bridges, or workflow runtimes. AgentOS owns the layer those systems do not reliably own together: canonical project operational state and governed transitions between versions of that state.

## 0. Reuse-first architecture policy

**Do not rebuild a wheel that already has a mature protocol or implementation.**

AgentOS must prefer adopting, wrapping, or adapting existing components over owning another copy of their functionality. New AgentOS code is justified only when the behavior is part of the unique State Kernel / execution-governance contract, or when no suitable standard/component exists.

Default adoption map:

| Problem | Prefer | AgentOS responsibility |
| --- | --- | --- |
| Tool/resource/context protocol | MCP | expose canonical state/work as MCP resources/tools; preserve AgentOS authorization and commit rules |
| IDE/editor integration | ACP | one ACP adapter or native agent + AgentOS MCP; do not maintain per-IDE extensions |
| Independent remote agents | A2A | map A2A tasks/artifacts to ExecutionEnvelope/StateDelta; never let remote agents commit HEAD directly |
| Web ChatGPT/Gemini/Claude execution | existing browser/web-agent bridges | implement a generic WebSessionAdapter contract; do not maintain vendor DOM automation unless unavoidable |
| Workflow/subgraph execution | LangGraph or existing workflow runtimes | treat workflow as one runtime behind a WorkItem; accept only semantic result/StateDelta |
| CI/ephemeral workers | GitHub Actions | use as a runtime/transport; keep state authority in AgentOS |
| Long-term/shared memory | Iranti/OACP-compatible/native provider | store refs/provenance/promotion policy; do not build another general vector-memory product |
| Human-readable handoff | Lead/OACP-style projections | export from canonical state; never treat exported files as authority |
| Provider/model APIs | existing SDKs/OpenAI-compatible/Gemini adapters | normalize output and enforce trust boundary |

A third-party component is treated as an **adapter/runtime/provider**, not as the canonical project authority. Reuse must never weaken the following invariants:

1. Project HEAD is owned only by the State Kernel.
2. External agents/models/browser sessions return proposals, not commits.
3. Runtime/session/provider identifiers are not project-state identifiers.
4. External side effects remain governed and auditable.
5. Replacing one wheel/provider must not require migrating canonical ProjectState.

### Web-agent rule

AgentOS should not create its own ChatGPT/Gemini/Claude browser automation stack when an existing bridge can reliably drive an authenticated browser session.

The AgentOS-owned boundary is a small transport-neutral contract such as:

```text
WebSessionAdapter
  discover_sessions()
  invoke(session_ref, ExecutionEnvelope)
  poll(result_ref)
  cancel(result_ref)
    -> untrusted SemanticResult / StateDelta proposal
```

Concrete browser bridges may implement that contract. Vendor DOM selectors, Chrome extension internals, login/session persistence, anti-bot workarounds, and conversation discovery belong to those bridges, not to the State Kernel.

This preserves the valuable behavior:

```text
Project HEAD
  -> bounded StateView + WorkItem
  -> WebSessionAdapter
  -> existing ChatGPT/Gemini/Claude web conversation
  -> semantic output
  -> StateDelta proposal
  -> validation / merge / commit
  -> new Project HEAD
```

without making AgentOS a browser-automation product.

## 1. Core thesis

**Project owns the state. Agent, model, IDE, conversation, provider, and runtime do not.**

An LLM/provider produces a proposal. A runtime executes work. A protocol transports requests. None of them may silently become the canonical project state.

AgentOS v2 separates:

1. **State Kernel** — canonical project state, immutable commits, concurrency, validation, provenance, audit.
2. **Execution Control Plane** — work items, leases, dispatch, runtimes, provider execution.
3. **Protocol Adapters** — MCP for tools/context, ACP for editor/agent UI, A2A for remote agent interoperability.
4. **Memory Providers** — durable facts/decisions/lessons that may be backed by AgentOS-native storage, OACP-style files, Iranti, or future providers.
5. **Runtime Providers** — raw model APIs, GitHub Actions, local workers, LangGraph, browser/desktop relays, or A2A agents.

## 2. Why v1 must evolve

`agentos.ir/v1` currently combines four concerns in one object:

- project state: goal, constraints, decisions, artifacts, pending tasks;
- execution intent: capability and payload;
- routing hints: runtime/provider policy inside context;
- continuation metadata: parent IR, hop count, completion metadata.

That was useful to prove cross-runtime continuation, but it creates ambiguity under concurrency. Project state is currently reconstructed from the most recently updated Distributed AgentOS task. That means two valid concurrent agents can race and whichever task updates last can accidentally become the apparent project state.

V2 inverts this relationship:

**Project HEAD is authoritative. Tasks are derived execution work against a specific base state.**

A task result may propose a state transition; it does not become state simply because the task completed.

## 3. State model

### 3.1 Project HEAD

Each project has exactly one authoritative HEAD pointer:

```text
Project
  project_id
  head_commit_id
  head_revision
  updated_at
```

HEAD points to an immutable `StateCommit`.

### 3.2 ProjectState

`agentos.state/v2` is a compact operational snapshot. It contains only information required to understand where the project is and what remains to be done.

```json
{
  "schema_version": "agentos.state/v2",
  "project_id": "agentmanager",
  "state_id": "state_<content hash>",
  "goal": "...",
  "constraints": [],
  "work_graph": {
    "items": []
  },
  "decision_refs": [],
  "artifact_refs": [],
  "memory_refs": [],
  "metadata": {}
}
```

Large logs, transcripts, provider output, raw tool results, secrets, and routing policy do not belong in ProjectState.

### 3.3 WorkItem

`agentos.work/v1` represents work, not state.

```text
work_id
project_id
base_state_id
instruction
capability
depends_on[]
priority
status
acceptance_criteria[]
runtime_policy
provider_policy
created_by
```

Work status is typed: `ready`, `blocked`, `leased`, `running`, `review`, `succeeded`, `failed`, `cancelled`.

### 3.4 ExecutionEnvelope

`agentos.exec/v1` is the transport-neutral input delivered to a runtime. It contains the selected WorkItem, a bounded StateView, required references, and execution policy. Runtime/provider placement is deliberately outside ProjectState.

### 3.5 StateDelta

Agents/providers return semantic output plus an optional `agentos.delta/v1` proposal:

```text
base_state_id
work_id
operations[]
artifact_additions[]
decision_candidates[]
memory_candidates[]
next_work_candidates[]
```

The model never creates a trusted StateCommit.

### 3.6 StateCommit

Only the State Kernel creates commits:

```text
commit_id
project_id
parent_commit_ids[]
base_state_id
result_state_id
author_principal
source_work_ids[]
validation_receipt
created_at
```

Commit IDs and state IDs are content-addressed where practical. This gives an auditable hash-linked lineage without requiring a blockchain.

## 4. Transaction semantics

A model output is a proposal, not a mutation.

```text
HEAD S10
  |
  +-- Work A executes against S10
  |      -> Delta A
  |
  +-- Work B executes against S10
         -> Delta B
```

When A finishes:

```text
validate Delta A
CAS HEAD == S10
commit -> S11
HEAD = S11
```

When B finishes later, B may not blindly replace S11.

The kernel must:

1. detect that B was based on S10;
2. compute whether Delta B conflicts with S10 -> S11;
3. auto-merge disjoint changes when safe;
4. otherwise create a merge/review work item;
5. keep both proposals and audit evidence.

No `latest updated task wins` rule is allowed in v2.

## 5. Continue semantics

`continue` is a project operation, not a replay of the last model/session.

```text
continue(project_id)
  -> read HEAD
  -> inspect active work
  -> if active work exists: wait/observe
  -> else select highest-priority ready WorkItem
  -> if no ready WorkItem, derive one only from explicit next-work policy or user instruction
  -> build bounded StateView
  -> dispatch
```

The meaning of `continue` therefore survives IDE, model, process, and device changes.

## 6. StateView: bounded context instead of prompt accumulation

A runtime should not receive the whole project database.

The kernel creates `agentos.view/v1` based on:

- project HEAD;
- current WorkItem;
- capability;
- principal permissions;
- relevant decisions/artifacts/memory;
- source trust/provenance;
- configurable token/size budget.

This is the only context a model should need for the current work. The view is disposable and never authoritative.

## 7. Memory is not canonical state

AgentOS must keep four layers distinct:

1. **Canonical operational state** — what is true now and what work is pending.
2. **Durable memory** — facts, lessons, known debt, stable decisions and preferences.
3. **Execution journal** — raw task/runtime/tool events and logs.
4. **Ephemeral model context** — one bounded StateView generated for one execution.

Memory promotion follows:

```text
observation
 -> candidate memory
 -> provenance/trust labeling
 -> validation/promotion
 -> durable memory
```

A retrieved web page, tool response, email, or model statement must never become durable project truth merely because it appeared in context.

Memory providers are pluggable. AgentOS may provide a minimal native store, but should be able to import/export or delegate to systems such as OACP-style project files or Iranti rather than rebuilding every memory feature.

## 8. Provenance and trust

Every externally sourced observation or promoted memory record should carry:

```text
source_kind
source_ref
content_hash
observed_at
principal/runtime
trust_class
untrusted_input flag
derivation refs[]
```

Untrusted input is allowed to influence a proposal, but policy gates decide whether it can affect canonical state.

## 9. Side-effect governance

State rollback cannot undo an email sent, deployment made, payment submitted, or external API mutation.

V2 therefore adds a side-effect ledger:

```text
side_effect_id
work_id
kind
target
intent_hash
status: prepared|committed|failed|compensated
idempotency_key
compensation_ref
receipt_ref
```

High-impact actions may require `prepare -> approve/validate -> commit` instead of direct execution.

## 10. Protocol alignment

### MCP — tools, resources, context

AgentOS should expose a standard MCP 2026-07-28 endpoint instead of requiring every compatible agent to learn a private REST API.

Candidate resources/tools:

```text
agentos://projects/{id}/head
agentos://projects/{id}/work
agentos://projects/{id}/decisions
agentos://projects/{id}/artifacts

project/open
project/continue
work/propose
work/status
memory/search
```

MCP is stateless at the protocol layer; `project_id`, `state_id`, `work_id`, and `commit_id` are explicit state handles. This matches the AgentOS architecture.

MCP Tasks may expose long-running AgentOS operations to MCP clients, but they do not replace internal lease/fencing semantics.

### ACP — editor UI boundary

Do not build and maintain separate VS Code, JetBrains, Zed, Neovim, and browser integrations.

Implement an AgentOS ACP adapter once. ACP-compatible editors can then host AgentOS as an agent UI.

Two supported patterns:

1. **Native agent + AgentOS MCP**: Codex/Claude/Gemini/Cursor remains the ACP agent and calls AgentOS through MCP for shared state.
2. **AgentOS meta-agent over ACP**: editor talks to AgentOS, which chooses/delegates to runtimes/providers itself. This gives the strongest guaranteed `continue` semantics.

ACP session IDs are UI/session handles only. They must never become project state IDs.

### A2A — remote agent boundary

Use A2A 1.0 for independent remote agents that support it:

```text
AgentCard discovery
A2A Task
Messages / Parts / Artifacts
streaming / async updates
```

Map A2A task output into an untrusted AgentOS StateDelta proposal. A remote A2A agent cannot directly commit ProjectState.

The current custom webhook transport remains useful for providers/runtimes that do not speak A2A, including GitHub Actions and browser/desktop relays.

## 11. Runtime integrations

AgentOS should not become a workflow framework.

- LangGraph can execute one WorkItem or sub-workflow and return a StateDelta.
- GitHub Actions can remain a push runtime.
- Raw OpenAI/Gemini-compatible APIs use Provider Bridge.
- A2A agents use the A2A adapter.
- Existing browser bridges drive authenticated web-agent sessions through the generic WebSessionAdapter.
- Local pull workers keep exact lease/fencing semantics.

The State Kernel does not care which one executed the work.

## 12. Human-readable compatibility

Keep `AGENTS.md` as a bootstrap pointer, not a state database.

Provide optional compatibility exporters:

- Lead Protocol-style handoff/current work summary;
- OACP-style facts/decisions/open threads/known debt;
- private GitHub `continuity/latest.json` mirror.

These are projections of canonical state/memory, not authorities.

## 13. Authentication direction

The root/runtime token must never become a universal IDE credential.

Short term:

- runtime/root service credentials remain separate;
- scoped IDE tokens: project.read, task.read, task.submit;
- lease/complete reserved for runtime principals.

Long term:

- prefer standard OAuth/OIDC authorization for human-facing MCP/HTTP access;
- preserve service credentials for runtime-to-runtime calls;
- avoid inventing a permanent proprietary login protocol if MCP/HTTP clients can use standard auth.

The current GitHub identity enrollment prototype is acceptable as a development bridge, but should not become the final protocol boundary before OAuth integration is evaluated.

## 14. Migration from CanonicalIR v1

Do not break the running production Core.

Introduce a compatibility translator:

```text
CanonicalIR v1
 -> ProjectState v2 snapshot
 -> one WorkItem from capability/payload
 -> context.runtime_policy/provider_policy -> WorkItem execution policy
 -> decisions/artifacts/pending_tasks -> refs/work graph
 -> parent_ir_id -> migration provenance only
```

During migration:

- v1 endpoints keep working;
- v2 state HEAD is shadow-written and compared against the v1 read model;
- no production routing switches to v2 until parity/concurrency tests pass;
- private continuity mirror may publish both `v1_current_ir` and `v2_head` temporarily.

## 15. Implementation order

### Phase A — State Kernel foundation

1. immutable ProjectState / StateDelta / StateCommit schemas;
2. SQLite project_heads + state_commits + state_blobs;
3. CAS commit semantics;
4. v1 -> v2 migration adapter;
5. tests for stale-base rejection and disjoint auto-merge.

### Phase B — Work graph

1. typed WorkItem IDs/dependencies/status;
2. task -> work mapping;
3. `continue(project)` resolves HEAD/work graph instead of latest task;
4. active-work duplicate prevention.

### Phase C — state views and memory promotion

1. bounded StateView builder;
2. provenance/trust model;
3. memory candidate/promotion interface;
4. native memory backend plus optional adapters.

### Phase D — protocol/adoption adapters

1. MCP 2026-07-28 server;
2. ACP adapter;
3. A2A 1.0 runtime adapter;
4. generic WebSessionAdapter wired to an existing browser bridge before considering any custom browser automation;
5. keep private REST as internal/backward-compatible API.

### Phase E — side effects and governance

1. side-effect ledger;
2. idempotency and compensation receipts;
3. policy/approval gates;
4. audit queries and operator UI/read model.

## 16. What AgentOS should explicitly NOT build

- another general-purpose vector memory database;
- another IDE-specific extension ecosystem;
- another generic agent-to-agent wire protocol;
- another tool protocol;
- another graph/workflow framework;
- vendor-specific browser automation when a maintained bridge already exists;
- vendor-specific conversation history as canonical state;
- implicit session-bound state.

## 17. Product boundary

The durable value of AgentOS is:

> **A vendor-neutral State Kernel that lets heterogeneous agents safely continue, coordinate, and commit work against one canonical project state.**

Everything else should be a protocol adapter, provider, runtime, projection, or reused external wheel.
