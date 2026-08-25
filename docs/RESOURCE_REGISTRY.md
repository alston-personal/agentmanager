# AgentOS Resource Registry v0.1

## Purpose

The Resource Registry is the durable world-model for node-local and externally reachable resources. It prevents every executor from rediscovering the same deployment topology from scratch.

Core rule:

> **Discover once, verify when stale, never rediscover blindly.**
> 一次發現，持續驗證，不重複失憶。

This is intentionally distinct from the existing AgentOS `Environment` manifest. `Environment` binds a Project to module versions/policies/node selection. `Resource Registry` describes concrete resources that exist in the operating environment: sites, services, repositories, paths, databases, devices, and similar infrastructure.

## Stable resource IDs

Resources use URI-like IDs:

- `site://studio.milkcat.org`
- `service://layoutlab-api`
- `repo://alston-personal/zeus-writer`
- `path://oracle/home/ubuntu/zeus-writer/website/dist`

The ID is identity; mutable facts belong in state fields.

## Three-state model

Each resource separates:

- **declared**: what AgentOS believes/configures as the intended topology.
- **observed**: facts last measured by `agentos-node`.
- **verification**: when/how observation was verified, errors, and freshness TTL.

Example:

```json
{
  "id": "site://studio.milkcat.org",
  "kind": "site",
  "declared": {
    "domain": "studio.milkcat.org",
    "framework": "astro",
    "repository": "alston-personal/zeus-writer",
    "repo_path": "/home/ubuntu/zeus-writer",
    "source_path": "/home/ubuntu/zeus-writer/website",
    "dist_path": "/home/ubuntu/zeus-writer/website/dist",
    "nginx_config": "/etc/nginx/sites-enabled/studio.milkcat.org"
  },
  "observed": {},
  "verification": {
    "status": "unverified",
    "last_verified_at": null,
    "ttl_seconds": 86400,
    "errors": []
  }
}
```

## Query-first algorithm

1. Resolve the resource ID from the registry.
2. Check computed `freshness.state`.
3. If `fresh`, use registered state directly.
4. If `stale` or `unverified`, execute a **targeted verifier** for that resource only.
5. Persist the new observation to the data layer.
6. Continue the task from the normalized resource record.

A full host scan is discovery/bootstrap behavior, not normal task behavior.

## Storage ownership

Logic/schema/tests live in `agentmanager`.

Mutable state defaults to:

```text
/home/ubuntu/agent-data/resources/registry.json
```

or `$AGENT_DATA_ROOT/resources/registry.json`.

This follows AgentOS Logic/Data Separation: source code says *how* to inspect; the data layer records *what is currently true*.

## CLI

```bash
agentos-node resource list
agentos-node resource list --kind site
agentos-node resource get site://studio.milkcat.org
agentos-node resource verify-site site://studio.milkcat.org
```

Registration is explicit:

```bash
agentos-node resource register site://studio.milkcat.org \
  --kind site \
  --ttl 86400 \
  --declared-json '{"domain":"studio.milkcat.org","framework":"astro"}'
```

## v0.1 verifier scope

`verify-site` currently performs only targeted checks:

- DNS resolution
- HTTPS HEAD/status/server/content-type
- declared local path existence/readability/writability
- Git branch/commit/origin when `repo_path` is declared

Future verifiers can add `service://`, `repo://`, port/route health, systemd units, and controlled mutations. Those should remain capability-gated rather than granting generic shell authority through the registry.
