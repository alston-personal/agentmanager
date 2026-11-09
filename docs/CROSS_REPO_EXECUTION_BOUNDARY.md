# Cross-Repository Governed Execution Boundary

Status: canonical architecture decision for Core #165, 2026-08-31

## Why this boundary exists

Issue #118 requires product implementation, product CI/request definitions, release logic, and product-specific runtime behavior to live in each canonical product repository. That does not imply each product repository must directly own or reach the privileged Oracle execution identity.

A product can own **what should be executed** while AgentOS Core/ONE owns **whether that privileged execution is authorized, how it is isolated, and how evidence is returned**.

The boundary therefore separates:

1. product source/request ownership;
2. Core authority and capability resolution;
3. privileged Oracle execution;
4. sanitized receipt/evidence.

## Fresh evidence and epistemic boundary

AgentOS Core #130 proved that an Oracle-labelled self-hosted runner can claim and complete governed jobs in `alston-personal/agentmanager`.

That proof is repository-local. It does not prove that the same runner can be directly claimed from every product repository.

Leopard Cat Tarot provides the first concrete cross-repository counterexample requiring diagnosis:

- product PR `alston-personal/leopardcat-tarot#41` owns a read-only `Production Parity Gate`;
- it requests `[self-hosted, Linux, ARM64, oracle]`;
- original run `33312465860` remained queued without a runner claim;
- after #130 recovery, the workflow was retriggered without semantic behavior changes at product commit `27610149eafe27872e71e0b4f2fdebded2d164fb`;
- retriggered run `33352392531`, job `99368137799`, was also observed queued with no execution steps started.

This evidence proves only that **agentmanager runner health is insufficient evidence of direct product-repository reachability**. It does not yet prove whether the cause is repository-scoped registration, organization scope, label/runner-group policy, concurrency, availability, or another GitHub Actions boundary. #165 must preserve this distinction.

## Ownership contract

### Product repository owns

- canonical product source;
- feature/fix/develop/main promotion state according to product policy;
- product tests;
- typed execution/deployment request definition;
- product artifact definition;
- product-specific parity criteria;
- exact candidate/accepted source identity.

### AgentOS Core / ONE owns

- Project Identity resolution;
- source/release-lane authority checks;
- capability/action allowlist;
- privileged Oracle execution boundary;
- project/capability-scoped secret brokering where required;
- idempotency/replay policy;
- sanitized receipt/evidence contract;
- cross-repository execution protocol.

Core does **not** regain ownership of product implementation merely because Core executes an authorized product request.

## Request contract

The target model is a versioned request equivalent to `agentos.execution-request/v1`.

Minimum semantic fields:

```json
{
  "schema": "agentos.execution-request/v1",
  "request_id": "<stable idempotency key>",
  "project_id": "<canonical project id>",
  "repository": "owner/repo",
  "source_ref": "<branch/tag/release ref>",
  "source_sha": "<exact 40-char sha>",
  "capability": "<governed capability id>",
  "environment": "<poc|staging|production|none>",
  "parameters": {},
  "expected_result": "<typed receipt/artifact contract>"
}
```

The request is not an authority token. Core resolves the canonical Project Identity and checks the requested ref/SHA/capability/environment against governance before privileged execution.

## Execution constraints

The generic boundary must reject:

- arbitrary shell strings;
- arbitrary executable paths;
- unrestricted argv tunneling;
- branch-only deployment identity without an exact SHA;
- unregistered project/repository substitutions;
- requests whose source SHA is not valid for the authorized source/ref relation;
- replay where the request contract is non-idempotent and replay was not explicitly authorized;
- Core-wide secret export to product repositories.

Execution should use a capability-scoped adapter, standardized product entrypoint/container, or another bounded runtime contract. A product may execute its own pinned code, but the privileged surface and available secrets/resources remain capability-scoped.

## Secret boundary

Product repositories must not receive generic Oracle/Core secrets simply because they need privileged execution.

If a capability requires a credential, it should be resolved at execution time from a project+capability-scoped secret authority. The receipt may record secret identity/version metadata when safe, but never the secret value.

## Receipt contract

A successful or failed request persists enough identity to reproduce what was attempted:

```json
{
  "schema": "agentos.execution-receipt/v1",
  "request_id": "...",
  "project_id": "...",
  "repository": "owner/repo",
  "environment": "...",
  "source_ref": "...",
  "source_sha": "...",
  "capability": "...",
  "artifact_digest": "...",
  "result_status": "...",
  "executor_identity": "...",
  "started_at": "...",
  "completed_at": "..."
}
```

Product-specific acceptance data may be attached as typed evidence, but credentials/private payloads are never returned by default.

## Transport is an implementation choice, not architecture authority

#165 must first diagnose why a product-repository Oracle job is not being claimed. After that, choose the narrowest safe transport.

Candidate transports include:

- product-owned request manifest/artifact consumed by Core/ONE;
- a project-scoped authenticated ONE/Realm request;
- a bounded GitHub App-mediated request;
- direct product-repository self-hosted execution only if runner scope/authority is deliberately configured and still satisfies secret/governance isolation.

The architecture does not require all products to use the same GitHub branch topology, and it does not require a product repository to host the privileged runner directly.

## First consumers

### Leopard Cat Tarot

The product repository owns parity/deploy request definitions. Core #165 supplies only the generic Oracle execution boundary. Retirement of historical `agentmanager` Tarot carriers still requires product-owned write/deploy replacement plus exact source/artifact runtime parity; a successful read-only parity gate alone is necessary but not sufficient.

### Vendor Reputation Service

The product repository owns monitored-source scheduling/request definitions and exact Vendor source identity. Core #165 may execute the authorized capability on Oracle and return a sanitized receipt. This is the intended path toward retiring agentmanager Vendor carriers #97/#99/#127 without copying Core secrets into Vendor.

## Relationship to other Core issues

- #130: accepted repository-local Oracle runner recovery evidence; not a cross-repository reachability guarantee.
- #66: accepted generic static release capability; does not by itself establish product source/artifact provenance or product-repo Oracle reachability.
- #96: Layout release-lane authority/live POC acceptance; may later consume this generic boundary but remains independently scoped today.
- #160: privileged Codex executor provider boundary; separate from product cross-repository execution.
- #118: repository separation authority; #165 blocks only the exact carrier-retirement steps that require Oracle execution.

## Acceptance

#165 is accepted only after all of the following are true:

1. the actual current runner scope/availability boundary is diagnosed and evidenced;
2. one product-owned deterministic read-only/no-secret request executes through the generic boundary;
3. exact product repo/ref/SHA is verified before execution;
4. capability authority is enforced without arbitrary shell/argv;
5. a sanitized execution receipt is persisted;
6. no Core-wide secret is copied into the product repository;
7. the product can keep implementation/request ownership outside `agentmanager`;
8. at least one #118 carrier-retirement path materially advances using the boundary.

Until then, #165 is a shared infrastructure worker, not a reason to pause unrelated product development.
