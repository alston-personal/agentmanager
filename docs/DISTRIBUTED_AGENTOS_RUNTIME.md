# Distributed AgentOS Runtime

## Goal

Evolve LeopardCat AgentOS from a runtime installed on every device into a distributed system where agents and devices share one portable handoff contract and invoke execution where capabilities actually live.

## Architectural rule

**Canonical IR is the continuity boundary. Runtime location is an implementation detail.**

A client, web agent, GitHub Actions job, local node, or future cloud worker must be able to receive the same IR, execute one declared capability, and return a derived continuation IR without requiring the previous agent's private conversational state.

## Components

### 1. Canonical IR (`runtime_core/canonical_ir.py`)

Transport-neutral JSON-safe state containing:

- goal and project identity
- requested capability and payload
- constraints and context
- artifacts and decisions
- pending tasks
- continuation metadata
- immutable lineage (`ir_id`, `parent_ir_id`)
- deterministic digest for integrity/idempotency support

The IR does not contain AgentOS filesystem paths or platform-specific behavior.

### 2. Remote Runtime (`runtime_core/remote_runtime.py`)

A capability-gated execution surface. Workers explicitly register supported capabilities. Unknown capabilities are rejected instead of interpreted as arbitrary shell commands.

Every successful execution returns a new Canonical IR whose `parent_ir_id` references the consumed IR.

### 3. Control Plane (`agent_core/control_plane.py`)

The existing node registry and task lease store remains the coordination authority for the MVP. Distributed runtime should extend this store rather than introduce a second scheduler.

Recommended next integration:

1. submit Canonical IR as the task payload;
2. lease by capability;
3. worker executes the IR;
4. persist result + continuation IR;
5. next compatible agent/runtime leases the continuation.

### 4. GitHub Actions Worker

`.github/workflows/distributed-agentos-worker.yml` is the first remote runtime adapter. It accepts Canonical IR through `workflow_dispatch`, executes only registered capabilities, and uploads the runtime result/continuation as an artifact.

GitHub Actions is **a worker, not the AgentOS brain**. Durable coordination and memory must not depend on ephemeral Actions runners.

### 5. Web Agent Adapter (next slice)

A Web Agent Adapter should only translate between a web agent's native request/response format and Canonical IR. It must not own project truth or invent a second state format.

Proposed interface:

```text
native agent state -> Canonical IR -> capability routing -> runtime
runtime result -> continuation IR -> native agent continuation
```

## Continuation protocol

A continuation is valid when:

1. its schema version is supported;
2. `parent_ir_id` references the consumed IR;
3. the consumed IR digest is recorded by the worker result;
4. the next requested capability is explicit;
5. private/transient agent chain-of-thought is not required to continue.

This means cross-agent continuity is based on explicit state, decisions, artifacts, constraints, and pending work rather than conversation replay.

## Security boundaries

- Never expose generic `shell.exec` as a public/default remote capability.
- Prefer small named capabilities with explicit validation.
- GitHub Actions uses read-only repository permissions unless a capability specifically requires more.
- Secrets stay in runtime-specific secret stores; Canonical IR should carry references/requirements, not raw long-lived credentials.
- Treat all IR received from web agents or external adapters as untrusted input.

## Migration path

### Phase A — current branch
- Canonical IR v1
- Remote Runtime contract
- GitHub Actions worker adapter
- continuation lineage tests

### Phase B
- Control Plane stores IR digest/lineage and continuation result
- worker adapter claims leased tasks instead of only manual dispatch
- idempotent continuation scheduling

### Phase C
- Web Agent Adapter
- agent-native importer/exporter adapters (ChatGPT/Gemini/Codex/etc.)
- automatic continuation routing based on capability + policy + cost

### Phase D
- devices become optional capability nodes rather than mandatory full Runtime installations
- local Runtime remains available for offline/private/high-trust capabilities
- remote runtimes can be GitHub Actions, server workers, browser workers, or specialized nodes

## End state

A device no longer needs a complete AgentOS runtime simply to participate. It needs either:

- a thin adapter capable of producing/consuming Canonical IR, or
- no local adapter at all when an external/web agent can invoke a remote runtime directly.

The durable system identity is the shared protocol + data/control planes, not a specific machine installation.
