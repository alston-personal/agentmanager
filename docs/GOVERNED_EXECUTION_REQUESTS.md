# Governed cross-repository execution requests

Core #165 introduces a narrow boundary between product-owned intent and Core-owned Oracle authority.

## Authority flow

`product manifest -> Project Identity/release-lane registry -> capability adapter -> Oracle execution -> sanitized receipt`

The product manifest is data, not executable content. `agentos.execution-request/v1` carries the project, canonical repository, exact 40-character source SHA, source ref, environment, capability, typed parameters, replay policy, and expected receipt contract.

Core is authoritative for the project/repository mapping, allowed release lane, capability-to-project mapping, exact parameter values, runtime path, health/public endpoint, and installed adapter. A request cannot create a new capability or change those values.

## Security invariants

- No shell, executable, argv, script path, filesystem path, sudo request, or secret may be tunneled through the manifest.
- Exact source SHA is mandatory; a branch name is never sufficient authority.
- Runtime remote, branch policy, HEAD, dirty-state allowlist, listener and endpoint/artifact evidence are verified by the capability adapter.
- HTTP(S) remote userinfo is stripped before it can enter receipts.
- Provider/Oracle credentials remain at the privileged execution boundary and are never returned in receipts.
- Read-only inspection is explicitly idempotent. Mutating adapters must define stronger replay/idempotency semantics before they can be registered.
- Product-specific source/build/deploy logic remains in the product repository. Core contains only the generic dispatcher, authority registry, and bounded capability adapters.
- Runtime branch policy is registry-owned. A product request cannot relax `source_ref` matching or opt into detached-HEAD acceptance.

## Receipt persistence

The clean smoke keeps repository permissions read-only and persists sanitized execution receipts as GitHub Actions artifacts for 30 days. This preserves independent evidence without granting the Oracle job contents-write authority or committing runtime evidence back into Core history.

A receipt records the request/project/repository/source/capability/environment identity, executor identity, exact runtime HEAD, sanitized remote, dirty-state result, endpoint/artifact evidence, and final status. It must never contain provider tokens, Oracle credentials, authorization codes, credential-bearing URLs, arbitrary command material, or secret values.

## Consumers

### Leopard Cat Tarot

Leopard Cat Tarot owns `.agentos/execution-requests/production-parity.json`. Core resolves that request against `governance/execution-authority.json` and invokes only `leopardcat_production_parity_inspect` on the Oracle runner. Its evidence level is `runtime_repo+deployed_artifact`, including local/localhost/public bundle parity.

### Vendor Reputation Service

Vendor Reputation Service owns `.agentos/execution-requests/production-runtime.json`. Core resolves it to the generic `repository_service_inspect` adapter. The request can select only the fixed production API listener; repository root, health path, expected health identity, dirty-state allowlist and detached-vs-branch runtime policy all remain registry-owned.

The Vendor runtime historically deploys an exact SHA with detached HEAD, so its authority explicitly permits only `detached_or_source_ref`; an arbitrary feature branch still fails closed. The health probe records only status, expected-identity match and response digest, not database contents or private Threads evidence. Its evidence level is `runtime_repo+service_endpoint`, so the receipt does not falsely label a health-response digest as a deployed artifact digest.

Both consumers are deliberately read-only. Production deployment and Vendor monitored-source mutation remain on retained carriers until separately governed mutating capabilities define exact replay/idempotency, secret-broker and sanitized-receipt contracts. This prevents #165 cleanup from silently widening deployment authority.

## Contaminated prototype

`core/issue-165-execution-v1` was useful as an experiment and evidence source but is not mergeable because earlier history contained credential-bearing evidence. The clean implementation must originate from current Core `main`; no commits are rebased or cherry-picked from the contaminated branch.
