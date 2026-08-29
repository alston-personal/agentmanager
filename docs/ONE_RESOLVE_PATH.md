# ONE Canonical Continuation Resolve Path

**Status date:** 2026-08-29

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

**Implemented and present in a live-accepted Core generation; resolve-specific end-to-end acceptance is still pending.**

The earlier deployment-channel blocker recorded on 2026-08-28 is no longer the current blocker. The canonical Core deployment path was subsequently repaired and Issue #64 produced a real Control Inbox acceptance against deployment generation 3 with `desired_core_commit == observed_core_commit == dedca4b1894987c4ed23fa43c442dbc11810b623` and `deployment_status=converged`.

The `/v1/resolve` endpoint commit (`f492b96081bd58b0634b68530e0d9f0ec89d739e`) is an ancestor of that accepted Core commit, so the resolve endpoint source is included in the live-accepted generation. This establishes **deployment inclusion**, not resolve-path execution proof.

What remains unproven is narrower and must not be overstated: no preserved real-path receipt currently proves that an enrolled Node authenticated to the live ONE `/v1/resolve` endpoint, resolved a canonical project identity, and received the expected continuation envelope. Likewise, the current ChatGPT Web surface has not yet been attested as an enrolled Realm node using that transport contract.

Therefore distinguish these states:

```text
source implementation              = PASS
included in accepted Core release  = PASS
Core service/controller transport  = PASS (Issue #64 evidence)
/v1/resolve authenticated request  = NOT YET EVIDENCED
fresh-chat ChatGPT -> ONE resolve   = NOT YET EVIDENCED
```

Do not reopen the obsolete deployment-host blocker unless fresh runtime evidence reproduces it. Do not claim full continuation closure merely because the endpoint source is deployed.

## Verification gates

1. Run `tests/test_resolve_facade.py` and `tests/test_realm_resolve_endpoint.py` against current/source-equivalent Core and preserve the focused result.
2. Use an enrolled controlled Node and perform an authenticated request to the **live** `POST /v1/resolve` endpoint.
3. Persist the response plus runtime generation/commit provenance as Core evidence/receipt.
4. Verify the returned envelope contains canonical Project Identity, integrity/mutation state, continuation availability, execution head availability, Node context, and explicit provenance.
5. Query canonical aliases from the live Governance Directory, including whether `Chamber` / `Echo` resolve to `metashield-protocol`; do not infer aliases from product/application identity registries.
6. Query the live NodeRegistry/Node Map so conceptual Nodes are distinguished from enrolled/live Nodes.
7. Connect and attest the ChatGPT Web logical surface to the same transport contract as an actual enrolled node/client identity, rather than treating a conversation as a node by assumption.
8. Open a fresh ChatGPT conversation, possibly on another machine, and enter only `繼續 metashield-protocol`.

Final PASS requires AgentOS to provide project identity/aliases, active goal, execution head, relevant Node/capability context, continuation/next action, and evidence provenance without GitHub/source rediscovery or alias guessing.

## Evidence interpretation

The following evidence must remain distinct:

- Issue #64 `.agentos/evidence/issue-64/control-inbox.json` proves the real Bootstrap Control Inbox -> ONE -> ControllerService route, not `/v1/resolve` semantics.
- A deployed commit containing `realm_server.py` proves release inclusion, not that an authenticated resolve request succeeded.
- Unit/endpoint tests prove source behavior under test conditions, not live Node identity or live Governance/continuation contents.
- Only a preserved live resolve receipt can close the resolve-specific runtime gate.
