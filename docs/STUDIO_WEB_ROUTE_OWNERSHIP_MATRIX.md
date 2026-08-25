# Studio Web Production Route Ownership Matrix

Status: Phase 0 baseline frozen from deterministic host audit (2026-08-25)

This matrix is derived from the active nginx configuration and public/local probes. It is a migration acceptance input, not a proposed target architecture.

## Public route ownership

| Public path | Current owner/type | Current origin/source | Baseline | Migration action |
|---|---|---|---|---|
| `/` | Platform static Astro shell | nginx root `/home/ubuntu/zeus-writer/website/dist` | HTTP 200, 11733 bytes | Extract into `studio-web`; preserve shell behavior |
| `/novels/` | Platform static alias | alias `/home/ubuntu/zeus-writer/website/dist/` | HTTP 200, 11733 bytes at route root | Move static ownership with `studio-web`; preserve generated novel/content routes |
| `/layout-lab/` | Intended platform-integrated product page, current ownership unresolved | currently falls through 443 site routing unless a generated static file exists | HTTP 200, 11733 bytes, same size as `/` | **NO-GO unresolved**: prove whether `dist/layout-lab/index.html` exists and has Layout Lab marker or current public route is only fallback HTML |
| `/prophecy/` | Independent static product | alias `/home/ubuntu/prophecy-verifier/` | HTTP 200, 13414 bytes | Keep independent; preserve nginx alias exactly |
| `/api/cookies` | Independent backend API | proxy `127.0.0.1:8088/api/cookies` | port 8088 root HTTP 200 | Keep backend independent; preserve proxy path/headers |
| `/dashboard` | Independent Next.js app | proxy `localhost:3000` | HTTP 200, 6979 bytes; backend root 404 is normal | Keep independent; preserve prefix and `/dashboard/_next/...` asset semantics |
| `/ipgenome` | Independent app | proxy `127.0.0.1:3002` | HTTP 200, 26639 bytes; backend root 200 | Keep independent; preserve websocket headers, 12m body limit and 300s timeouts |
| `/ipgenome/api/` | Independent API | proxy `127.0.0.1:3002` | same backend | Keep independent; preserve path/body/timeout semantics |
| `/iftv` | Independent Next.js/app | proxy `localhost:3005` | HTTP 200, 15664 bytes; backend root 404 is normal | Keep independent; preserve websocket/subpath behavior |
| `/iftv/renders/` | Independent static artifact alias | `/home/ubuntu/if-tv-station/public/renders/` | active alias | Preserve exact alias; do not copy into `studio-web` |
| `/iftv/assets/uploads/` | Independent static artifact alias | `/home/ubuntu/if-tv-station/public/assets/uploads/` | active alias | Preserve exact alias |
| `/iftv/assets/intros/` | Independent static artifact alias | `/home/ubuntu/if-tv-station/public/assets/intros/` | active alias | Preserve exact alias |
| `/chamber-api` | Chamber backend | proxy `localhost:3011` | backend root 404 is normal | Keep independent; preserve websocket/proxy headers |
| `/echo` | Echo web app | proxy `localhost:3010` | HTTP 200, 17147 bytes; backend root 404 is normal | Keep independent |
| `/echo/chamber-extension.zip` | Echo exact static artifact | `/home/ubuntu/metashield-protocol/web-feed/public/chamber-extension.zip` | exact nginx alias | Preserve exact alias/download behavior |
| `/echo/README_TEST.md` | Echo exact static artifact | `/home/ubuntu/metashield-protocol/web-feed/public/README_TEST.md` | exact nginx alias, markdown content type | Preserve exact alias and MIME behavior |
| `/hanzi` | Independent Hanzi app | proxy `localhost:3020` | HTTP 200, 11694 bytes; backend root 200 | Keep independent |
| `/acas/` | Independent ACAS app | proxy `localhost:8090/` | HTTP 200, 15254 bytes; backend root 200 | Keep independent; preserve trailing-slash proxy semantics |
| `/acas` | Redirect contract | nginx redirect | redirects to HTTPS `/acas/` | Preserve redirect exactly |

## Platform extraction boundary

### Move into `studio-web`

- Astro platform source currently under `/home/ubuntu/zeus-writer/website`.
- Generated platform shell/static pages currently served from `/home/ubuntu/zeus-writer/website/dist`.
- Platform-owned content routes under the Astro source tree, including currently discovered `agentos`, `tiandao`, `testimony`, `translator`, `language-notes`, `omnirealm`, `tech-notes`, and other routes found by source inventory.
- `/novels/` static ownership, after proving which generated content belongs to the platform versus Zeus Writer publication inputs.
- Future `/vendors/` Vendor Reputation UI belongs to this platform integration layer, while its backend/data service may remain separately deployable.

### Do not move into `studio-web`

- Prophecy Verifier implementation/assets.
- Dashboard backend/app.
- IP Genome backend/app.
- IF TV backend/app and rendered/uploaded/introduction assets.
- Chamber API.
- Echo app and its independently owned downloadable artifacts.
- Hanzi app.
- ACAS app.

These remain independent products and are integrated by nginx/integration contracts.

## Baseline invariants

Current public probe results:

```text
/             200  11733
/dashboard    200   6979
/layout-lab/  200  11733
/prophecy/    200  13414
/novels/      200  11733
/ipgenome     200  26639
/iftv         200  15664
/echo         200  17147
/hanzi        200  11694
/acas/        200  15254
```

Current local backend root probes:

```text
3000  -> 404  (expected baseline)
3002  -> 200
3005  -> 404  (expected baseline)
3010  -> 404  (expected baseline)
3011  -> 404  (expected baseline)
3020  -> 200
8088  -> 200
8090  -> 200
```

A migration test must compare application-specific paths and content markers, not assume every backend `/` must be HTTP 200.

## Critical unresolved checks before Phase 1 mirror acceptance

1. **Layout Lab ownership/regression check** — current `/layout-lab/` response byte size equals `/`. Verify filesystem existence and content marker of `dist/layout-lab/index.html`, source route ownership, and same-origin API path. A fallback homepage returning 200 is not a passing Layout Lab test.
2. **Novels/content extraction boundary** — the Zeus Writer checkout is dirty and contains modified/untracked publication content. Never use `git reset`, `git clean`, or remote-only extraction as the migration source until every live source file has been inventoried and preserved.
3. **Static assets** — compare referenced assets and generated route manifests between the live site and mirror build; HTTP 200 fallback HTML must not satisfy asset acceptance.
4. **Prefix apps** — explicitly probe Dashboard `_next` assets and representative IF TV/Echo paths after any routing change.
5. **Mutator ownership** — update all workflows, Action Relay `site.sync_build`, and Resource Registry only after the independent mirror has passed acceptance.

## Cutover rule

The nginx 443 root remains `/home/ubuntu/zeus-writer/website/dist` until a clean independent `studio-web` mirror build passes this matrix plus the migration contract. No backend proxy or independent static alias moves merely because the platform shell moves.
