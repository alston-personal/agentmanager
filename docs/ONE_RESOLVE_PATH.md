# ONE Canonical Continuation Resolve Path

**Status date:** 2026-08-28

## Purpose

Normal continuation must use AgentOS through its control plane. A cognitive executor must not rediscover AgentOS or project truth by searching GitHub/source code, generic memory, application registries, or local workspaces.

> **Use AgentOS; do not rediscover AgentOS from its source code.**

## Source-level path

```text
enrolled Node
    -> ThinClientTransport.resolve(project)
    -> ONE POST /v1/resolve
    -> Resolve Facade
        -> Governance Directory project identity
        -> project continuity/latest.json when present
        -> project execution-head.json when present
        -> Node bootstrap/capability context
    -> agentos.resolve/v1 envelope
```

Implemented source paths:

- `agent_core/resolve_facade.py`
- `agent_core/realm_server.py` (`POST /v1/resolve`)
- `agentos_node/thin_client_transport.py` (`resolve`)
- `tests/test_resolve_facade.py`
- `tests/test_realm_resolve_endpoint.py`

## Project identity rule

Project aliases are accepted only from the canonical Governance Directory project entity (`id`, `name`, or `metadata.aliases`).

During migration, an existing `AGENT_DATA_ROOT/projects/<project_id>` directory may satisfy an **exact project ID** lookup. It does not create aliases.

The resolver must not infer project aliases from:

- application-owned `identity-registry.json` files;
- GitHub repository names;
- workspace names;
- free-form STATUS/memory prose;
- model memory or conversation guesses.

Ambiguous aliases are errors, not guesses.

A concrete collision discovered during implementation: `projects/metashield-protocol/identity-registry.json` is a MetaShield/Echo product identity registry containing user/platform identities such as `sunlake` and Facebook bindings. It is **not** AgentOS Project Identity and must never be used by `project.resolve`.

## Resolve envelope

Current v1 composition can return:

- canonical project identity and declared aliases;
- active goal when a canonical `agentos.ir/v1` continuation is present;
- projected continuation IR fields;
- `agentos.execution-head/v1` when present;
- authenticated Node bootstrap/capability context;
- recommended next action when present;
- explicit availability/provenance for missing fields.

`last_receipt` is intentionally reported unavailable until receipts have a canonical project-indexed lookup. The resolver must not guess the last relevant receipt.

## Maturity

**Implemented in source; runtime verification blocked by deployment-channel configuration.**

The source and regression tests are committed, but no valid focused Core test run or Oracle live acceptance receipt has yet been produced for these commits. Unrelated application workflows triggered by repository pushes are not evidence for this capability.

A governed Realm Fabric deployment was deliberately triggered on 2026-08-28 using the existing `.github/workflows/deploy-realm-fabric-core.yml` push path. Run `33135873181` failed before SSH or installation because `DEPLOY_HOST_SOURCE` was empty. The workflow resolves that value from `secrets.AGENTOS_DEPLOY_HOST || secrets.N8N_BASE_URL`; `DEPLOY_USER` and the SSH port were present, but neither host source resolved. Therefore the failure is currently classified as a **deployment-channel configuration blocker**, not a resolver/code failure.

Do not bypass this by inventing a parallel deploy transport. Repair or deliberately replace the canonical deployment channel, then re-run the same deployment and verification gates.

The current ChatGPT conversation is also **not** evidence of end-to-end closure: this ChatGPT environment still cannot invoke the AgentOS ONE control plane directly and had to use repository access while implementing the missing path.

## Verification gates

1. Restore a valid canonical Oracle deployment host source for Realm Fabric (`AGENTOS_DEPLOY_HOST` or an explicitly approved replacement/fallback).
2. Re-run the governed Realm Fabric deployment for current source.
3. Run `tests/test_resolve_facade.py` and `tests/test_realm_resolve_endpoint.py` in the deployed/source-equivalent environment.
4. Enroll or use a controlled test Node and perform an authenticated `/v1/resolve` request.
5. Persist the result as Core evidence/receipt.
6. Query the live Governance Directory and verify canonical Project Identity aliases, including whether `Chamber` / `Echo` resolve to `metashield-protocol`.
7. Query the live NodeRegistry/Node Map so conceptual Nodes are distinguished from enrolled/live Nodes.
8. Connect and attest the ChatGPT Web logical Node to the same transport contract.
9. Open a fresh ChatGPT conversation, possibly on another machine, and enter only `繼續 metashield-protocol`.

Final PASS requires AgentOS to provide project identity/aliases, active goal, execution head, relevant capabilities, continuation/next action, and evidence pointer without GitHub/source rediscovery or alias guessing.
