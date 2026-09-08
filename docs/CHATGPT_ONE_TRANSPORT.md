# ChatGPT → ONE Transport Authority

Status: Core #179 implementation candidate. This document defines transport-selection authority; it does not claim that ChatGPT Web already has a native direct ONE tool.

## Current reality

ChatGPT Web has a working bootstrap path into AgentOS ONE through GitHub Issue #50:

```text
ChatGPT Web
  -> ChatGPT GitHub connector
  -> Bootstrap Control Inbox (#50)
  -> Oracle bridge
  -> ONE
```

The GitHub issue/comment layer is a temporary transport mailbox. It is not the control-plane authority. ONE remains authoritative for allowed actions and Node/Realm routing.

The bootstrap transport is intentionally replaceable by an AgentOS MCP/App without changing ONE or Node contracts.

Separately, Core #152 / PR #167 is implementing an MCP adapter for the Antigravity built-in Gemini executor. That work does not by itself make ChatGPT Web a native ONE/MCP client.

## Routing invariant

Transport selection is authority-driven, not convenience-driven.

For a typed AgentOS control-plane intent, resolve transports in this order when they are both authorized and available:

1. `one_direct`
2. `agentos_mcp_app`
3. `control_inbox`

`github_actions` is not in the allowed set for control-plane intents.

For explicitly typed workflow intents (CI, tests, build, package, release, deployment, declared evidence workflow), `github_actions` is an allowed workflow carrier.

## Fail-closed rule

A ONE-side failure does not expand authority.

If `one_direct`, `agentos_mcp_app`, and `control_inbox` are unavailable or fail, a control-plane request fails as a transport/control-plane error. The caller must not start a GitHub Actions workflow merely because an Oracle self-hosted runner is reachable.

This is the transport equivalent of the Core invariant:

> Capability does not imply authority.

## Intent examples

Control-plane intents include Realm/Node status and discovery, capability/governance resolution, governed executor discovery/liveness, session handoff, declared runtime control, and governed node execution requests.

Workflow intents include CI/tests, build/package, explicit release, explicit deployment, and separately authorized evidence workflows.

Natural-language classification is intentionally outside `agent_core.transport_routing`. A caller must first produce a typed intent; the resolver then enforces the transport authority for that class. Unknown intent classes fail closed.

## Machine contract

- Policy: `governance/transport-routing.json`
- Resolver: `agent_core/transport_routing.py`
- Regression tests: `tests/test_transport_routing.py`

The policy requires deterministic routing for the same typed intent and availability snapshot. Switching conversation, model, or executor must not change the authorized carrier merely because a different tool looks convenient.

## Acceptance boundary

### Active continuation read candidate (#179)

Owner: AgentOS Core / ONE continuation and transport boundaries. This candidate
closes the missing read route; it is not a live ChatGPT hydration acceptance.

- `GET /v1/controller/continuation/active`: controller-authenticated private
  executor projection of the existing ONE active selector and resolved Canonical
  IR. It reuses the existing executor-safe projection and refuses a response if
  that projection would truncate or redact the Canonical IR. It never selects
  work from a workspace or caller-supplied project/path.
- `GET /v1/controller/continuation/active/identity`: same authentication and
  generation validation, returning only bounded project/index/IR identifiers,
  observation time, and explicit `canonical_ir_included=false`,
  `hydration_complete=false`, `credential_exposed=false` flags.
- Both reject query overrides. Missing, stale, malformed or changing active
  state fails closed with `ONE_IR_HEAD_UNRESOLVED`; no raw error detail is returned.
- The public bootstrap command `agentos.continuation.inspect` uses only the
  identity endpoint. Its envelope retains `agentos.control-command/v0.1`, short
  expiry, trusted author and command deduplication. The current Oracle bootstrap
  scope requires `node_id=oracle-core-node` and empty `args`. No URL, path,
  project override or arbitrary action is accepted. The bridge independently
  validates the identity response, including observation freshness, and drops
  all extra response fields before storing or posting it.

The command remains disabled unless explicitly added to the host-local
`AGENTOS_CONTROL_ALLOWED_ACTIONS` during governed installation. Code presence
does not change the live allowlist. No Node task, shell or Actions job is used.

The private endpoint must be consumed by a trusted private adapter that retains
the controller credential outside model context. Never publish its response in
Issue #50, an artifact, a repository or client configuration. The identity-only
receipt is an observation, not Canonical IR and not execution authority. Old
receipts cannot establish the current active generation. Full continuation still
requires a fresh private read; no working state may be reconstructed from the
identity receipt or chat history.

Closure: accept the source through `core/integration`, deploy the exact accepted
generation through governed runtime authority, enable only the bounded inspect
action, and prove a fresh public identity read plus a private adapter read bind
the same generation. Exercise stale/changed-head refusal on a disposable
acceptance fixture. Until the private adapter is available in ChatGPT, report
hydration as unresolved even if the public inspect command succeeds. Neither
deployment nor capability availability grants protected-main publication.

The static resolver/tests prove the no-fallback authority rule, but they do not alone prove ChatGPT Web transport transparency.

Core #179 remains incomplete until a fresh ChatGPT conversation demonstrates a Realm/Node control-plane request resolving through Control Inbox/ONE with no Actions workflow invocation. A later AgentOS MCP/App may replace Control Inbox after equivalent acceptance evidence exists.
