# AgentOS Node Contract v0.1

`agentos-node` is the node-local canonical discovery and responsibility-resolution surface. It is not a second manager, a second role registry, or an authority-granting shell bridge.

## Runtime entrypoint

On the Oracle self-hosted node identity:

```text
/home/agentos-node/.local/bin/agentos-node
```

The runtime bundle is derived from the AgentOS logic repository and reads mutable state from `/home/ubuntu/agent-data`.

## Harvest

```bash
agentos-node harvest
```

Advertises node-supported query/observation capabilities, including:

- `governance.resolve`
- `governance.get`
- `governance.list`
- `resource.query`
- `resource.register`
- `resource.verify.site`

Harvest describes what the node surface can route/query. It does not grant execution authority.

## Responsibility resolution

Before implementing reusable or cross-project capability:

```bash
agentos-node governance resolve capability://network.port.allocate
```

Expected current result:

```text
manager://port
```

An active exclusive owner means the caller must reuse/extend that owner instead of creating a competing implementation.

Examples:

```bash
agentos-node governance get role://governance.spec_steward
agentos-node governance list --kind manager
agentos-node governance list --kind role
```

## World-model query

```bash
agentos-node resource get site://studio.milkcat.org
agentos-node resource list --kind site
```

If a registered resource is fresh, use it. Only stale/unverified records should invoke targeted verification:

```bash
agentos-node resource verify-site site://studio.milkcat.org
```

## Canonical authority boundaries

The node surface is an index/router over existing authorities:

| Concern | Authority |
|---|---|
| Role semantics | `.agent/roles/registry.yaml` |
| Responsibility/provider resolution | Governance Directory |
| World/environment state | Resource Registry |
| Port allocation | `manager://port` / Port Manager |
| Project state | Agent Data project registry |
| Execution authorization | Governance Registry / effect-derived authority |

`agentos-node` must not silently take ownership from those components.

## Required executor startup protocol

For system/cross-project work:

```text
1. harvest
2. governance resolve(required capability)
3. query relevant registered resources
4. targeted verify only if stale/missing
5. reuse/extend active owner
6. only if unresolved: discover → register provider/resource
7. authorize effect
8. execute
9. persist receipt/evidence
```

This protocol operationalizes:

> Discover before invent. Resolve before implement. Verify before trust.

## Current verified evidence (2026-08-25)

Oracle validation proved:

- six dependency-free contract tests passed;
- runtime entrypoint installed under the `agentos-node` identity;
- `harvest` advertises governance/resource capabilities;
- `network.port.allocate` resolves to exclusive `manager://port`;
- `site://studio.milkcat.org` is queryable directly from registered verified state;
- Governance Directory audit completed with zero errors.

Warnings are not hidden. At validation time the Service Registry and Watchdog source still disagreed on `moltbot-gateway.service` vs `os-lobster.service`; that requires targeted runtime verification before correction.
