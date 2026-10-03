# Executor Self-Adoption Contract

Status: canonical AgentOS Node integration contract, 2026-10-02.

## Goal

AgentOS Core must not hard-code how Claude Code, Codex, Gemini, Antigravity, or any future executor is installed, authenticated, invoked, cancelled, or supervised.

Core owns the lifecycle and governance contract. Each executor integration owns the provider-specific knowledge required to satisfy that contract.

The desired boundary is:

```
AgentOS Scheduler
  -> Node / Thin Client
  -> Executor Manager
  -> provider adapter
  -> provider runtime
  -> governed receipt
```

The Thin Client remains the transport, heartbeat, policy, task, and receipt boundary. An executor never becomes a Node identity merely because it is installed.

## Provider-owned responsibilities

Every executor provider MUST define all of the following without requiring AgentOS Core to infer private implementation details.

### 1. Identity

- `executor_id`: stable canonical ID.
- `provider_id`: provider family.
- `executor_class`: scheduler-visible class.
- `mode`: CLI, GUI, bridge, API, relay, or another bounded mode.
- `capabilities`: semantic capabilities contributed when READY.

### 2. Discovery

The provider owns discovery across the environments it supports.

Discovery MAY inspect:

- PATH;
- known vendor install locations;
- registered application locations;
- running processes;
- AgentOS surface inventory;
- provider-owned relay/service health;
- provider-owned session bridge descriptor.

Discovery MUST NOT:

- read or copy credentials;
- widen file permissions;
- scrape private provider state not explicitly exposed by the provider adapter;
- convert arbitrary filesystem paths or arbitrary argv into execution authority.

A running process, installed binary, authenticated session, and routable executor are independent facts.

### 3. Readiness

Providers MUST report separate dimensions:

- `installed`
- `reachable`
- `authorized`
- `routable`
- `healthy`

AgentOS derives lifecycle state from those dimensions. A provider MUST NOT claim READY from binary presence alone.

Recommended lifecycle states:

- `READY`
- `DISCOVERED`
- `AUTH_REQUIRED`
- `INSTALL_REQUIRED`
- `REGISTRATION_REQUIRED`
- `UNHEALTHY`
- `DISABLED`
- `UNAVAILABLE`

### 4. Invocation

A provider adapter owns the fixed mapping from bounded AgentOS semantic work to the provider runtime.

The caller MUST NOT supply:

- executable path;
- arbitrary argv;
- shell;
- environment secrets;
- credential locations.

The provider integration decides how to invoke its own runtime and must expose a bounded `invoke()` entrypoint.

### 5. Cancellation and timeout

Each provider MUST define:

- whether cancellation is supported;
- how an `invocation_id` maps to provider execution;
- maximum execution timeout;
- what happens when cancellation cannot be guaranteed.

### 6. Health

The provider MUST distinguish at least:

- executable/runtime absent;
- runtime present but provider unavailable;
- auth/session missing or expired;
- transport/relay/bridge unhealthy;
- concurrency/session lock busy;
- provider throttled/rate-limited;
- provider healthy.

Health output must be safe to persist.

### 7. Receipt

Every invocation MUST produce a governed receipt containing only bounded, non-secret evidence.

Required receipt identity:

- `executor_id`
- `provider_id`
- `invocation_id`
- `started_at`
- `completed_at`
- `successful`
- `classification`
- safe result metadata

Credentials, tokens, cookies, raw private session state, and unrestricted stdout/stderr are not canonical receipt fields.

### 8. Concurrency

Each provider MUST declare its concurrency model:

- stateless / parallel-safe;
- single process;
- single authenticated session;
- single GUI profile;
- provider-specific mutex/lease.

The scheduler must not infer this from process count.

### 9. Adoption

An existing installation must be adopted without reinstalling when possible.

Provider adoption is:

```
discover
-> inspect provider-owned readiness
-> register adapter
-> run bounded smoke invocation
-> emit adoption receipt
-> advertise capability
```

Reinstall is a repair path, not the default adoption path.

## Canonical provider interface

Each integration should implement the semantic equivalent of:

```python
class ExecutorProvider:
    executor_id: str
    provider_id: str
    executor_class: str

    def discover(self) -> dict: ...
    def capabilities(self) -> list[str]: ...
    def health(self) -> dict: ...
    def invoke(self, request: dict) -> dict: ...
    def cancel(self, invocation_id: str) -> dict: ...
    def receipt(self, invocation_id: str) -> dict: ...
```

The exact Python shape may evolve, but Core behavior MUST depend on these semantics rather than provider filenames, executable names, install paths, or browser details.

## Provider profile

Each provider owns one declarative profile under:

```
.agentos/executors/<executor-id>.json
```

The profile documents how that provider expects to be discovered and governed. It is metadata, not execution authority. Executable paths in a profile must be provider-owned allowlisted classes, never caller input.

Required profile fields are demonstrated in `.agentos/executors/_template.json`.

## Core responsibilities

AgentOS Core owns only:

- trusted provider registration;
- task validation;
- scheduler routing;
- capability publication;
- invocation lifecycle;
- concurrency lease enforcement;
- cancellation orchestration;
- receipt persistence;
- state transitions;
- reconciliation;
- policy and secret boundaries.

Core MUST NOT encode provider-specific PATH guesses once an executor provider exists.

## Acceptance rule

An executor becomes scheduler-routable only after all of these pass:

```
provider discovered
AND provider authorized
AND provider health healthy
AND bounded smoke invocation successful
AND receipt persisted
```

Anything less remains non-routable and is reported with the provider's explicit state.

## Migration rule for VOPC5750

The current hard-coded discovery in `agentos_node/executor_reconcile.py` is transitional.

Migration order:

1. Claude Code provider profile + adapter.
2. Codex provider profile + adapter.
3. Gemini provider profiles by mode (CLI / Web / Antigravity where applicable).
4. Antigravity provider profile + adapter.
5. Reconcile reads trusted registered providers rather than `shutil.which()` knowledge.
6. VOPC5750 reruns adoption and smoke receipts.
7. Repeat the same reconcile path for DQA03, MBPR, Oracle, and future joined Nodes.

This preserves the rule: Node Join converges desired state; provider integrations explain how their own executor becomes governable.
