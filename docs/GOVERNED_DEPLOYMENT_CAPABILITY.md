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

The initial registry binds **source-only** `studio.public-site` to the existing Studio static route/home publishers and diagnostic scripts, and `studio.layout-lab` to the existing LayoutLib materialize/promote/parity providers. The registry is an *inventory of named carriers*, not a declaration that their runtime execution is currently authorized. Other product publishers (Mio PDCA/persona, Threads Galaxy, Vendor, ArcanaForge, Character Blueprint and Mission Control) must be classified against the existing #175 carrier inventory first, not silently migrated.

Studio has confirmed provisional Oracle TLS 443 site-file root at `zeus-writer/website/dist`, public identity mismatch on Layout Lab and WoW, and outstanding old-root writer references. AgentOS PR #2257 remains **Draft**; this Core contract must NOT unblock its promotion automatically. Production cutover requires effective Nginx-vhost authority, writer classification, immutable Studio release, tested rollback, protected API and product parity, followed by a second publish generation.

## Extending the same capability

Future product adapters register a fixed `target_id` backed by existing #165 execution authority and a product-owned release lane. Core owns only request validation, gate semantics, machine-readable receipts, lease/replay coordination, registry and audit. Product repositories own build, migrate, artifact creation and verification details. Each accepted capability must persist outside individual LLM sessions under #1672, and remain discoverable through the existing Resource/Capability mechanisms.

**This change is intentionally a reusable library plus tests, not a standalone new service.** The next implementation slice is to call the gate from an already-authorized #165 / Runner Window release preflight after the current Studio cutover and provider work is verified; do not introduce a new arbitrary workflow dispatch API or mark the library as runtime-active before that happens.

Related canonical work: #165, #1672, #175, #118, #213, #331, AgentOS PR #2257 and Studio PR #151.
