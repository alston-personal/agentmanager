# Executor Provider / Identity Boundary

Status: canonical Core architecture decision, 2026-08-31. Origin: #117 architecture return; execution follow-ups #72, #160, #161.

## Problem

Oracle has intentionally different identities for infrastructure execution and interactive/Antigravity executor state:

- the GitHub/AgentOS runner executes as `agentos-node`;
- Antigravity Claude/Codex binaries and their user-scoped identity/session/config live under `ubuntu`;
- private Antigravity extension roots are not intended to be traversed by `agentos-node`.

This is a security boundary, not a file-permission bug. A regression worker must not solve executor discovery by widening filesystem access, copying credentials/binaries, or introducing arbitrary privileged shell execution.

## Decision 1 — provider-specific privileged relays

Privileged executors whose usable binary/identity are owned by another OS identity are exposed through a **fixed-provider governed relay/service boundary**.

For Codex, #160 uses a separate ubuntu-owned fixed-provider Codex relay/service/root. It must not turn the existing Claude relay into a capsule-controlled arbitrary executable gateway.

The Codex relay contract is bounded by these invariants:

1. provider is fixed by service configuration, not capsule input;
2. executable discovery is allowlisted to the expected Antigravity Codex extension path class;
3. the executor naturally uses ubuntu-owned user identity/config, but the relay never reads/returns/copies credential or session contents as data;
4. request input is an AgentOS execution contract, not generic shell/argv authority;
5. receipt output is sanitized and provenance-bearing;
6. no chmod/sudo/credential relocation/binary copying is used to bypass identity separation;
7. deployment/publication authority remains separate from executor availability.

A future multi-provider relay is not prohibited, but it requires a separate acceptance proving that provider selection is a closed canonical allowlist with equivalent isolation. It is not the default solution for #117.

## Decision 2 — bounded Claude diagnostics

#72 may run minimal diagnostics inside the existing ubuntu-owned Claude boundary:

- supported auth/status probe;
- deterministic normal headless print;
- deterministic restricted headless print where supported.

This authority is diagnostic-only. It does not authorize generic shell/argv, setting mutation, credential/session inspection, permission widening, or timeout increases.

Persisted evidence should contain only safe execution metadata needed to distinguish failure classes: CLI/provider version, command class, timing, return code, timeout status, safe stdout/stderr size/digest/classification, and deterministic expected-token result.

## Decision 3 — managed/passive vs ONE-aware executor

Experience hydration and executor protocol awareness are distinct capabilities.

### Managed/passive executor

A trusted AgentOS adapter may:

1. resolve project/Realm/task identity;
2. discover canonical Experience;
3. project bounded hydration;
4. invoke a target executor;
5. collect output and governed receipt.

The underlying model does not need to understand AgentOS itself. This is a valid executor mode and is sufficient for #117 baseline-vs-hydrated Master Experience Floor acceptance when evidence isolation and authority constraints pass.

### ONE-aware executor/node

A higher-capability executor participates in a model-neutral AgentOS startup/continuation handshake and can use governed protocol surfaces to discover/query allowed state/capabilities and emit progress/state-delta/evidence/receipt back to ONE.

This capability is tracked by #161. It must reuse existing Realm/ANCP/node/receipt/canonical-state primitives where possible and must not create a new canonical memory store or imply arbitrary mutation authority.

#161 is intentionally **not** a dependency of #117. Otherwise a focused Experience hypothesis test would become blocked on a general bidirectional executor protocol redesign.

## Acceptance and evidence principle

Executor availability, executor awareness, Experience hydration, and mutation/publication authority are four independent dimensions. Passing one does not imply the others.

A receipt/evidence record should therefore make these claims separately where applicable:

- which provider/executor identity actually ran;
- which governed adapter/relay authorized execution;
- which hydration artifact/digest was supplied;
- whether the executor was passive or ONE-aware;
- what capabilities/authority were exposed;
- exact result/timing/error evidence;
- whether any state mutation or deployment authority was exercised.

This separation is required so a successful model response cannot be misreported as proof of privileged authority, ONE awareness, or durable cross-executor continuity.
