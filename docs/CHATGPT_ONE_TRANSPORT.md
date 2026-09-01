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

The static resolver/tests prove the no-fallback authority rule, but they do not alone prove ChatGPT Web transport transparency.

Core #179 remains incomplete until a fresh ChatGPT conversation demonstrates a Realm/Node control-plane request resolving through Control Inbox/ONE with no Actions workflow invocation. A later AgentOS MCP/App may replace Control Inbox after equivalent acceptance evidence exists.
