# Governed cross-repository execution requests

Core #165 introduces a narrow boundary between product-owned intent and Core-owned Oracle authority.

## Authority flow

`product manifest -> Project Identity/release-lane registry -> capability adapter -> Oracle execution -> sanitized receipt`

The product manifest is data, not executable content. `agentos.execution-request/v1` carries the project, canonical repository, exact 40-character source SHA, source ref, environment, capability, typed parameters, replay policy, and expected receipt contract.

Core is authoritative for the project/repository mapping, allowed release lane, capability-to-project mapping, exact parameter values, runtime path, public origin, and installed adapter. A request cannot create a new capability or change those values.

## Security invariants

- No shell, executable, argv, script path, filesystem path, sudo request, or secret may be tunneled through the manifest.
- Exact source SHA is mandatory; a branch name is never sufficient authority.
- Runtime remote, branch, HEAD, dirty-state allowlist, listener, built artifact and public artifact are verified by the capability adapter.
- HTTP(S) remote userinfo is stripped before it can enter receipts.
- Provider/Oracle credentials remain at the privileged execution boundary and are never returned in receipts.
- Read-only parity inspection is explicitly idempotent. Mutating adapters must define stronger replay/idempotency semantics before they can be registered.
- Product-specific source/build/deploy logic remains in the product repository. Core contains only the generic dispatcher, authority registry, and bounded capability adapters.

## First consumer

Leopard Cat Tarot owns `.agentos/execution-requests/production-parity.json`. Core resolves that request against `governance/execution-authority.json` and invokes only `leopardcat_production_parity_inspect` on the Oracle runner.

The first adapter is deliberately read-only. Production deployment remains on the retained legacy carrier until a separately governed deploy capability is designed and accepted. This prevents #165 cleanup from silently widening deployment authority.

## Contaminated prototype

`core/issue-165-execution-v1` was useful as an experiment and evidence source but is not mergeable because earlier history contained credential-bearing evidence. The clean implementation must originate from current Core `main`; no commits are rebased or cherry-picked from the contaminated branch.
