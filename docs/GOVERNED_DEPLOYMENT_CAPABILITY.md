# Governed Deployment Capability v1

**Status: source-only contract, not registered for runtime execution or production deployment.**

This extracts the cross-product **deployment lifecycle** from duplicate release procedures while **reusing** AgentOS Core #165 `agentos.execution-request/v1`, ONE `agentos.executor-job/v1`, the single authorized Runner Window, Resource Registry, deployment-owner workflows and existing product-specific providers. It does **not** create a second dispatcher, privileged executor, scheduler, SSH API or GitHub deployment workflow.

## Contract

`agentos.deployment-capability/v1` identifies an exact registered `target_id`, `project_id`, immutable 40-hex `source_commit`, fixed `source_ref`, `operation`, `expected_generation`, plus opaque request/deployment IDs. It deliberately excludes caller-controlled paths, repositories, release carrier names, scripts, commands, runtime users, URLs, environment and credentials. Such fields fail closed. Target owner and fixed existing carrier names are stored only in `governance/deployment-capabilities.json`.

Operations are `inspect`, `stage`, `promote`, `verify`, and `rollback`. A pure, deterministic `evaluate_deployment_gate` returns `PASS` or `BLOCKED` with structured reasons, and **always** `execution_performed=false` and `release_receipt=false`. A `PASS` gate is not executor authority or proof of deployment.

No caller can select an arbitrary adapter. Production mutations still require the existing Core execution authority, dedicated product adapter, node capability scope, live lease, replay/fencing protection, exact SHA, and final independent receipt.

## Minimum evidence for release

- **Inspect:** source and target observed, read-only result only. Full `nginx -T` not readable is *not* a valid claim of effective configuration.
- **Stage:** previous observed generation matches, approved execution authority, active exclusive lease, exact verified source and artifact integrity, reproducible build.
- **Promote:** all stage checks PLUS verified served root, every active old-root writer reconciled, correct critical routes and protected APIs, a prepared **and rehearsed** rollback, and accepted live authority. Source-only targets cannot pass.
- **Verify:** live serving root, route identity, protected APIs, independent terminal release receipt. HTTP 200 alone is insufficient.
- **Rollback:** prior immutable release available, valid authority/lease/observed generation and rollback plan. Rollback completion must have its own independent receipt.

There must be only one active release writer per target/generation. Legacy and new channels may not be updated simultaneously, and destructive cutover waits for the other recovery channel to be verified. A source branch merge, static asset copy, workflow dispatch acknowledgement, or test success never becomes a success receipt.

## First adopters and migration safety

The registry binds four **source-only** targets to their own existing carriers: `agentos.public-console` to the immutable AgentOS Console release; `agentos.shared-auth-dashboard` to the existing shared Dashboard blue/green release; `studio.public-site` to existing Studio static route/home publishers and diagnostics; and `studio.layout-lab` to existing LayoutLib materialize/promote/parity providers. The registry is an *inventory of named carriers*, not a declaration that their runtime execution is currently authorized. Other product publishers (Mio PDCA/persona, Threads Galaxy, Vendor, ArcanaForge, Character Blueprint and Mission Control) must be classified against the existing #175 carrier inventory first, not silently migrated.

Studio has confirmed provisional Oracle TLS 443 site-file root at `zeus-writer/website/dist`, public identity mismatch on Layout Lab and WoW, and outstanding old-root writer references. AgentOS PR #2257 remains **Draft**; this Core contract must NOT unblock its promotion automatically. Production cutover requires effective Nginx-vhost authority, writer classification, immutable Studio release, tested rollback, protected API and product parity, followed by a second publish generation.

## AgentOS and Studio: two distinct public production domains

Both sites consume **the same Core deployment lifecycle contract**, but are distinct release targets, source authorities, serving systems and rollback scopes. The registry now contains:

| Target | Canonical source | Existing carrier | Runtime/acceptance | Release policy |
| --- | --- | --- | --- | --- |
| `agentos.public-console` | `agentmanager/main` | `oracle-agentos-login-control-plane-release.yml` → `deploy_distributed_control_plane.sh` | `agentos-control-plane.service`, public `agentos.milkcat.org`, `inspect_distributed_control_plane.py` | Independent control-plane generation, public login/session, Realm/admin, rollback |
| `agentos.shared-auth-dashboard` | `agentmanager/main` | Existing `deploy_dashboard_blue_green_user.sh`, currently invoked inside the immutable AgentOS login release workflow | Shared Next Dashboard OAuth API, Dashboard blue/green acceptance | Separate **logical** dependency and verification identity; currently physically coupled in the existing workflow |
| `studio.public-site` | `studio-web/main` | Existing reusable Studio static route / home release workflows | `studio.milkcat.org`, Astro origin and product markers; retain Dashboard API proxy | Isolated immutable Studio static generation and Nginx root cutover |
| `studio.layout-lab` | `layoutlib/main` | Existing LayoutLib materialize / promote / parity providers | Studio-hosted `/layout-lab/` and seven-file SHA parity | Bounded static subroute, cannot mutate Studio homepage authority |

**Dependencies, not lockstep deployment:** AgentOS public console **and** Studio public site depend on independently healthy `agentos.shared-auth-dashboard`; the Studio-hosted Layout Lab depends on the Studio serving root. This is a compatibility/acceptance graph, not an instruction to deploy both websites together. One site's update MUST NOT silently trigger or overwrite the other site's production generation. The existing AgentOS login carrier currently rolls the shared Dashboard before the AgentOS Console; therefore it is a *coupled operational carrier* requiring two phase-specific receipts and independent rollback verification. A later extraction may separate its adapters only after their actual current writer/owner state is verified, reusing the existing Blue/Green mechanism.

**AgentOS critical acceptance:** `agentos.milkcat.org` must serve a public, non-operator-token login, correct Google/GitHub/Facebook/LINE callbacks and same-origin cookie/session, authenticated `/welcome` / `/my-one`, correct platform 401 vs 403, protected Realm actions, existing Runner Window/ONE routes, current `agentos-control-plane.service` source SHA and unit identity. Authorization must not be inferred from whether a page returned 200.

**Studio critical acceptance:** `studio.milkcat.org` must serve the correct Studio-controlled static root, exact route-specific content for `/world/`, `/wow-addons/`, `/layout-lab/` and others, preserved generated Persona/Mio content and Vendor/Studio APIs, authenticated Dashboard/OAuth continuity, then an independent Studio SHA/root/rollback Receipt. No fallback homepage may satisfy a page identity check.

**Boundary risks:** `agentos.milkcat.org` Console is NOT Studio, and `/agentos/` creative content hosted on Studio is NOT the AgentOS runtime. A shared OAuth service does not imply common domain cookies, common Nginx root, automatic admin rights, or authorization to overwrite either site's release. The registered carriers are inventory-only until actual authorized ONE/Runner Window binding and site-specific production receipts. The `dependencies_verified` input is a verified-provider evidence slot, **never an end-user attestation or approval grant**.

## Extending the same capability

Future product adapters register a fixed `target_id` backed by existing #165 execution authority and a product-owned release lane. Core owns only request validation, gate semantics, machine-readable receipts, lease/replay coordination, registry and audit. Product repositories own build, migrate, artifact creation and verification details. Each accepted capability must persist outside individual LLM sessions under #1672, and remain discoverable through the existing Resource/Capability mechanisms.

**This change is intentionally a reusable library plus tests, not a standalone new service.** The next implementation slice is to call the gate from an already-authorized #165 / Runner Window release preflight after the current Studio cutover and provider work is verified; do not introduce a new arbitrary workflow dispatch API or mark the library as runtime-active before that happens.

Related canonical work: #165, #1672, #175, #118, #213, #331, AgentOS PR #2257 and Studio PR #151.

## ONE runtime inspection bridge — source integration (2026-11-12)

This slice **reuses the existing** `agentos.executor.job` Action Relay provider registry and introduces only two fixed, bounded **read-only** ONE jobs: `deployment.agentos.inspect` and `deployment.studio.inspect`, each with registered `oracle-deployment-inspector` and exact `site://` workload reference. The caller may not supply paths, shell, URLs, alternate project, credentials, port, arbitrary request body, or release operation. The registered providers run only fixed local `systemctl --user show agentos-control-plane.service` and/or allowlisted, localhost-bound TLS public endpoint probes, and classify on-disk Studio vhost root only if the known site-file target is valid. No configuration text, HTML, stderr or environment data is returned.

**Evidence boundary:** A healthy AgentOS service + HTTP 200 cannot prove its immutable release SHA, OAuth, Realm routes or rollback. The Studio on-disk site file is not necessarily the effective Nginx configuration; even the exact public root marker cannot prove all active writers are migrated. Both inspectors therefore intentionally return `verdict=FAIL` / `successful=false` with a specific classification until richer independent acceptance is available. Neither authorizes deploy, reload, rollback or lease mutation. Gate `PASS` is not runtime completion.

This creates the source-side ONE inspection registration and allows a next-stage *real* Oracle readback Receipt after the new Action Relay code is installed through the existing governed runtime release. A GitHub merge/CI result alone does not prove runtime installation, live availability or correctness. The existing fixed `layoutlib.production.parity.inspect` remains an independent product-specific verifier and does not become an implicit root-cutover action.

Next step is separately approved, bounded **stage/promote** adapter integration using the existing #165 execution authority, product-owned carriers and Runner Window only after read-only inspectors, installed version and proof sources are attested. Do not accept caller-created boolean `proof` objects as execution authority; authoritative evidence must be derived inside existing trusted adapters from immutable receipts and current runtime observations.
