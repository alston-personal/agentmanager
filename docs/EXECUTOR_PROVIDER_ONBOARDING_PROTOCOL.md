# Executor Provider Onboarding Protocol

Status: canonical onboarding procedure for executor providers.

A new executor integrates by satisfying this protocol. AgentOS Core should not need provider-specific edits after this boundary exists.

## Provider onboarding flow

1. Copy `.agentos/executors/_template.json` to:
   `.agentos/executors/<executor-id>.json`.

2. Fill the provider-owned fields:
   - stable identity;
   - discovery strategies;
   - readiness semantics;
   - capabilities;
   - invocation mapping;
   - cancellation behavior;
   - concurrency / mutex model;
   - smoke test;
   - receipt evidence;
   - adapter module.

3. Implement the provider adapter.

4. Provider adapter must expose the semantic contract:
   - `discover()`
   - `capabilities()`
   - `health()`
   - `invoke(request)`
   - `cancel(invocation_id)`
   - `receipt(invocation_id)`

5. Run provider self-check.

6. AgentOS reconcile validates the profile and loads only explicitly registered trusted adapters.

7. AgentOS runs the provider smoke test.

8. Only a successful governed smoke receipt allows the executor to become routable / READY.

## Provider self-completion principle

When an executor is asked to join AgentOS, the executor should read:

- `docs/EXECUTOR_SELF_ADOPTION_CONTRACT.md`
- `.agentos/executors/provider-profile.schema.json`
- `.agentos/executors/_template.json`

It then owns the work required to complete its integration package.

The executor should not ask AgentOS Core to guess vendor-specific installation paths, authentication state, invocation syntax, GUI session details, or cancellation behavior.

Its integration package is considered complete when it supplies:

```
.agentos/executors/<executor-id>.json
+ provider adapter
+ provider tests
+ bounded smoke test
+ receipt projection
```

## Self-completion output

The joining executor should produce a bounded integration report:

```json
{
  "schema": "agentos.executor-provider-onboarding/v0.1",
  "executor_id": "...",
  "profile_valid": true,
  "adapter_registered": true,
  "discovered": true,
  "authorized": true,
  "healthy": true,
  "smoke_receipt_ok": true,
  "routable": true,
  "state": "READY"
}
```

If it cannot complete one dimension, it must stop at the corresponding non-routable state instead of pretending READY.

Examples:

- executable found, login missing -> `AUTH_REQUIRED`
- runtime found, adapter absent -> `REGISTRATION_REQUIRED`
- adapter registered, smoke failed -> `UNHEALTHY`
- not installed -> `INSTALL_REQUIRED`

## No Core patch rule

Adding a normal executor provider should not require editing:

- scheduler routing internals;
- Thin Client transport;
- Realm Fabric;
- Core executable lookup tables.

A Core patch is required only when the protocol itself needs a new generic capability.

This is the key extensibility guarantee:

```
new executor
-> reads protocol
-> implements its provider package
-> reconcile validates
-> smoke proves
-> capability becomes routable
```

## Security boundary

Provider self-completion is not arbitrary self-registration authority.

Core still controls:

- which adapter modules are trusted/allowlisted;
- which semantic capabilities may be advertised;
- which profile schema version is accepted;
- which secrets remain inaccessible;
- which smoke evidence qualifies;
- whether the provider becomes routable.

An executor may describe how it should be integrated, but it cannot grant itself unrestricted shell, secret access, or publication authority.

## Existing providers to migrate

The first providers expected to complete this protocol are:

- Claude Code
- Codex
- Gemini CLI
- Gemini Web
- Gemini via Antigravity
- Antigravity

Provider-specific modes should remain distinct where their auth, concurrency, or invocation boundaries differ.
