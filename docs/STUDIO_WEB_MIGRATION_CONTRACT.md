# Studio Web Extraction — Zero-Regression Migration Contract

Status: PRE-CUTOVER / audit in progress

## Goal

Extract the platform website for `https://studio.milkcat.org` from the Zeus Writer repository into an independent `studio-web` project without changing the externally observable behavior of any existing route or integrated service.

This is a platform extraction, not a product consolidation. `studio-web` owns the platform shell, navigation, static platform pages and integration contracts. Product logic/backends remain in their product repositories unless an audit proves a concrete reason to move them.

## Current production ownership that must not be treated as one folder

Known current nginx integration surface includes:

- `/` — static Astro platform shell, currently rooted at `/home/ubuntu/zeus-writer/website/dist`, with SPA/404 fallback to `/index.html`.
- `/novels/` — aliases the current website dist tree.
- `/prophecy/` — alias to `/home/ubuntu/prophecy-verifier/`.
- `/api/cookies` — reverse proxy to `127.0.0.1:8088`.
- `/dashboard` — reverse proxy to localhost port 3000; Next.js assets use `/dashboard/_next/...`.
- `/ipgenome` and `/ipgenome/api/` — reverse proxy to port 3002 with upload/long-timeout semantics.
- `/iftv` — reverse proxy to port 3005, plus static aliases for renders/uploads/intros.
- `/chamber-api` — reverse proxy to port 3011.
- `/echo` — reverse proxy to port 3010, plus exact static aliases for extension/readme artifacts.
- `/hanzi` — reverse proxy to port 3020.
- `/acas/` — reverse proxy to port 8090, with `/acas` redirect behavior.
- `/layout-lab/` — integrated static product page; same-origin API integration is governed separately and must be preserved when present.

The live audit is authoritative over this preliminary list. Any route discovered by the audit automatically becomes part of the acceptance matrix.

## Confirmed coupling points that MUST migrate together

### 1. nginx ownership

Current `server_name studio.milkcat.org` production root is `/home/ubuntu/zeus-writer/website/dist`. Extraction may change only the platform static root/aliases that actually belong to the platform. Existing product reverse proxies, websocket/SSE headers, exact aliases, redirects, body limits and timeouts must be preserved byte-for-behavior unless explicitly accepted otherwise.

### 2. GitHub workflow ownership

At minimum these workflows are migration-sensitive:

- `.github/workflows/oracle-sync-layoutlab-static.yml`
- `.github/workflows/oracle-integrate-layoutlab-official-site.yml`
- `.github/workflows/validate-action-relay.yml`
- `.github/workflows/validate-resource-registry.yml`

The complete list must come from the live audit. No workflow may continue to deploy/sync the old Zeus Writer website after cutover.

### 3. AgentOS Action Relay ownership

`agentos_node/action_relay.py` currently implements `site.sync_build` with `/home/ubuntu/zeus-writer` and its `website` directory as the allowlisted production site checkout. This must move to the new canonical site resource only after parallel acceptance passes.

The governed action must remain deterministic and allowlisted; migration is not authorization to add arbitrary shell execution.

### 4. AgentOS Resource Registry ownership

`site://studio.milkcat.org` currently declares:

- repository: `alston-personal/zeus-writer`
- branch: `master`
- repo path: `/home/ubuntu/zeus-writer`
- source path: `/home/ubuntu/zeus-writer/website`
- dist path: `/home/ubuntu/zeus-writer/website/dist`

Cutover is incomplete until the canonical resource declaration points to `studio-web` and a fresh verification succeeds. Validation workflows must also stop re-registering the old declaration.

## Migration phases

### Phase 0 — Read-only audit and baseline

No production mutation.

Required outputs:

1. exact active nginx config and all routes;
2. repo/source/build/deploy ownership for every platform/product surface;
3. listener → process/service → repo correlation;
4. workflow/action/registry mutators that can change the site;
5. source-tree coupling from `website` to parent Zeus Writer files/assets/packages/env/symlinks;
6. external and localhost baseline matrix;
7. unresolved unknowns and risk classification.

### Phase 1 — Independent parallel site

Create an independent `studio-web` repository/checkout and reproduce the current platform build without changing nginx production root.

Required properties:

- no write to the old Zeus Writer checkout except normal pre-existing workflows explicitly invoked for baseline comparison;
- build output is independent of parent Zeus Writer files unless dependencies are intentionally copied/extracted and documented;
- old production continues serving traffic;
- new dist is tested through a local/alternate origin using production-equivalent routing semantics;
- hashes/content markers for important static assets/pages are compared where appropriate.

### Phase 2 — Integration-contract migration

Prepare, but do not yet irreversibly cut over:

- nginx candidate config changing only platform-owned static root/aliases;
- Action Relay `site.sync_build` ownership to the new site resource;
- Resource Registry declaration to `studio-web`;
- all site-mutating workflows to new paths/repository;
- Layout Lab and other platform page integrations to the new shell source.

All changes must retain an explicit old-root rollback value.

### Phase 3 — Controlled cutover

Cut over only after every GO gate passes. Validate nginx config before reload. Keep the old Zeus Writer website checkout/dist untouched and immediately reusable during the acceptance window.

### Phase 4 — Post-cutover acceptance

Run the same baseline matrix against production. Verify route behavior, assets, redirects, APIs, websocket/SSE flows where applicable, representative non-mutating functional checks, registry freshness and governed deploy behavior.

### Phase 5 — Decommission coupling

Only after sustained acceptance:

- remove obsolete Zeus Writer website ownership references;
- prevent validation/deployment workflows from re-registering or rebuilding the old site;
- leave product repositories/backends independent;
- record final topology and rollback retirement decision.

## GO gates

Cutover is GO only if all are true:

- independent `studio-web` build succeeds from a clean checkout;
- every discovered public route passes its baseline-equivalent check;
- platform static pages/assets are present under expected paths;
- all reverse-proxied backends remain healthy and path semantics are unchanged;
- Dashboard `/dashboard/_next/...` assets remain reachable;
- upload/body-size and long-timeout integrations retain their nginx semantics;
- websocket/SSE integrations retain upgrade/buffering semantics where applicable;
- exact aliases/download artifacts remain reachable;
- redirect behavior remains equivalent;
- Action Relay no longer targets Zeus Writer for site sync and its tests pass;
- Resource Registry verifies the new `studio-web` declaration as fresh/verified;
- no enabled workflow can silently rebuild/redeploy the old website as canonical production;
- nginx configuration validation passes before reload;
- rollback has been rehearsed as a deterministic config/root restoration, not an improvised manual procedure.

## Automatic NO-GO / rollback triggers

Any of the following is a NO-GO before cutover or a rollback trigger after cutover:

- any existing route changes expected HTTP status or loses its content marker unexpectedly;
- any API health/representative request regresses;
- any expected static asset returns fallback HTML or 404;
- Dashboard or another prefix-based app loses its subpath assets;
- websocket/SSE behavior regresses;
- any product upload/function path is broken by body-size, timeout or proxy path changes;
- Resource Registry still resolves the old Zeus Writer checkout as canonical after intended cutover;
- `site.sync_build` or any workflow still writes/builds the old website as the production source;
- nginx validation fails;
- an unresolved route/service owner remains in the production config.

## Rollback invariant

Until final acceptance, rollback must require only restoring the previous nginx site config/static root (and, if already switched, the prior Action Relay/Resource Registry declaration), validating nginx, reloading it, and rerunning the baseline. The old `/home/ubuntu/zeus-writer/website/dist` must remain intact throughout this window.

## Evidence rule

Do not mark extraction complete from a successful build alone. Completion requires evidence for all ownership planes:

1. public/runtime route plane;
2. filesystem/build plane;
3. nginx integration plane;
4. process/service/port plane;
5. GitHub workflow plane;
6. AgentOS Action Relay plane;
7. AgentOS Resource Registry plane;
8. rollback and post-cutover baseline plane.

The read-only AgentOS audit receipt is the authoritative input for expanding this contract before Phase 1 execution.
