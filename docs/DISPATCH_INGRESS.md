# AgentOS Dispatch Ingress Contract

Status: canonical routing rule for new callers

## Core rule

Normal callers MUST submit work to ONE by capability.

They MUST NOT select a GitHub runner, hostname, machine label, or concrete node merely because that executor happens to exist today.

Preferred request shape:

```json
{
  "schema": "agentos.controller-dispatch/v0.1",
  "action": "host.inspect.nginx",
  "payload": {}
}
```

ONE selects an eligible execution target.

## Selection

Current v0.1 selection considers:

1. node is online
2. node advertises the requested capability
3. pending queue depth
4. heartbeat freshness
5. stable node ID as deterministic final tie-breaker

The selection algorithm may evolve without changing caller contracts.

## Explicit target

`node_id` / `target_node` is an override path for:

- diagnostics
- conformance testing
- break-glass recovery
- hardware-specific work where the target itself is part of the task semantics

It is not the normal scheduling interface.

## GitHub runner window

GitHub Actions is an ingress/transport, not the scheduler.

New automation MUST NOT encode:

```yaml
runs-on: [self-hosted, Linux, ARM64, oracle]
```

as its normal routing decision.

Legacy workflows may remain temporarily grandfathered while migrated.

Target model:

```text
Caller / GitHub / Agent
  -> ONE dispatch ingress
  -> capability + policy + load
  -> selected Participant / Node / Executor
  -> execution
  -> correlated receipt
```

Adding a future executor must not require changing existing callers when it provides an already-known capability.

## Capability examples

```text
host.inspect.nginx
video.generate
browser.session.operate
agent.surface.inspect
llm.reason
social.publish
```

Names must describe semantic capability rather than product or machine identity.

## Receipt requirements

A dispatch receipt must preserve at least:

- dispatch_id
- task_id
- requested capability/action
- selected node/Participant
- selection mode
- selection reason
- queue time
- final execution receipt correlation

A caller must be able to distinguish:

```text
requested
-> routed
-> queued
-> executed
-> receipt accepted
```

## Migration rule

When touching a grandfathered direct-Oracle workflow, prefer migrating its execution request to this dispatch contract rather than creating another runner-specific workflow.

The legacy allowlist is a retirement list, not a template.
