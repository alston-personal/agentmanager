# ADR — Responsibility Resolution Before Implementation

- **Date:** 2026-08-25
- **Status:** Accepted
- **Constitution:** `2026.08.25.2`
- **Role set:** `2026.08.25.2`

## Context

AgentOS already had project registries, capability boundaries, a Port Manager, role definitions, Spec Steward, Watchdog, and a Resource Registry. However, an Agent could still fail to know that an existing owner/manager/provider existed and independently implement a second solution.

The Layout Lab work exposed this concretely: before consulting the existing Port Manager and service responsibilities, a new deployment path could easily have introduced a second allocator or service-management mechanism.

This is organizational-memory drift, not merely missing documentation.

## Decision

Add the core constitutional principle `responsibility_resolution`:

> Before implementing reusable or cross-project capability, resolve existing owner, manager, provider, and policy. If a valid responsibility already exists, reuse or extend it rather than creating a parallel implementation.

The Governance Directory becomes the runtime responsibility resolver. It indexes existing canonical authorities but does not replace them.

Canonical role semantics remain in `.agent/roles/registry.yaml`. Runtime/world state remains in Agent Data. Authorization remains with the Governance Registry and effect-derived authority model.

## Required execution sequence

```text
Intent / required capability
        ↓
Governance Directory resolve
        ↓
existing active owner/provider?
   ┌────┴────┐
  yes        no
   ↓          ↓
reuse/      targeted
extend      discovery
   ↓          ↓
Governance  register reusable
Authorization capability/resource
   ↓
execute → receipt
```

## Consequences

Positive:
- reduces duplicate managers/services;
- makes historical system knowledge actionable rather than passive;
- allows cross-model executors to discover the same organizational structure;
- gives drift tooling an explicit invariant to test.

Costs:
- reusable work now has a resolution step before implementation;
- Directory freshness and provider ownership must themselves be monitored;
- responsibility conflicts require escalation rather than silent overwrite.

## Migration

1. Existing Port Manager becomes the exclusive owner of `network.port.*` allocation capabilities.
2. Canonical role registry is mirrored into the Governance Directory; role prose is not duplicated there.
3. Stale role instances remain visible but are excluded from active resolution.
4. Existing Resource Registry remains the world-model authority and is resolved through Cartographer.
5. Future reusable system capabilities must register an owner/provider or explicitly document why a new provider is justified.

## Non-goals

The Directory does **not** grant execution authority. It only resolves responsibility/provider location.

Execution remains governed by:

`Capability → Intent → Authorization → Ledger → Effect → Receipt`.
