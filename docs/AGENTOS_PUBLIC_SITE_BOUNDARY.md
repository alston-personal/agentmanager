# AgentOS public website / operator console split (candidate, 2026-11-06)

Approved presentation: Studio = products/fiction/character life; AgentOS public = system explanation/responsibilities/capabilities; AgentOS operator = private dispatch/approval/node/health/receipts.

## Source implementation

- `dashboard/app/about/page.tsx` is a **public content candidate** for AgentOS introduction.
- `dashboard/app/agents/page.tsx` is a **public content candidate** of active roles from `.agent/roles/registry.yaml`. It is an allowlisted snapshot: NOT live worker health.
- Never claim these routes are published on `agentos.milkcat.org` without an Oracle-origin deployment/route receipt.
- The existing dashboard root is still an operational shell. **Do not mount it openly on the AgentOS public origin.**
- Proposed `/console/` must receive real server-side operator authorization before relocating the shell; no client-only gate and no `noindex` as substitute.

## Public and private separation

Do not publish work item contents, role memories, node addresses, runtime health, auth cookies, queue details or receipts as public static HTML. Keep Studio `/dashboard/api/*` product contracts, OAuth callback, wardrobe, likes, project APIs, and AgentOS `/api/`, `/v1/`, `/join` upstream contracts unchanged.

For production public pages, invoke the existing `capability://web.static-index.render` provider and require both its render receipt and no-JavaScript inspection. Candidate Next metadata alone is not a compliant production static-index release. The publishing owner must reconcile actual Nginx mappings and avoid duplicating Studio Web draft PR #131.

## Release gates

1. Oracle-origin mapping: confirm `agentos.milkcat.org` actual source, process, port, route precedence and Nginx config; check `agentmanager/dashboard` is really authoritative before mounting.
2. Authorization: prove anonymous requests cannot access operator pages, role internal records, assignment actions or node metadata.
3. Compatibility: preserve Studio login/callbacks and `/dashboard/api/*` as-is, AgentOS `/api/`, `/v1/`, `/join`; check real client requests, not just HTTP 200.
4. Public discoverability: shared static-index render receipt, page title/heading/summary/canonical, share metadata, robots/sitemap and proper status code.
5. Deploy with pinned source and rollback. Accept only with production node evidence; protected `main` merge and release require explicit authorization.

## Status

Source-only public content candidate. No DNS, Nginx, service, deployment, private console, or production claim.
