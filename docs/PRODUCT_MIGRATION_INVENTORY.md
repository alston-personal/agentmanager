# Product Migration Inventory

Status: Issue #118 migration phase 2, 2026-08-31

This document classifies non-Core work that still appears in `alston-personal/agentmanager`. It does not authorize destructive cleanup. A carrier or historical branch is retired only after a canonical product-owned replacement exists and runtime/deployment parity has been verified.

## Current classifications

| Product / scope | Canonical repo | Agentmanager residue | Current decision |
| --- | --- | --- | --- |
| Vendor Reputation | `alston-personal/vendor-reputation-service` | PR #97 patrol artifact carrier, #99 calibration carrier, #127 monitored-source scheduler | Keep temporarily. Product implementation is already outside Core, but Oracle execution/scheduling carriers still depend on Core infrastructure. Migrate after a governed product-owned runner/capability path is verified. |
| ArcanaForge | `alston-personal/arcanaforge` | PR #136 POC release carrier | Keep until #66 provides a governed static-release path and an exact ArcanaForge source/artifact receipt can drive `/poc/arcanaforge/`. |
| LayoutLib | `alston-personal/layoutlib` | Core-side deploy/governance residue tracked by #96 | Keep only generic deployment/promotion adapter. Layout implementation and product tests stay in `layoutlib`; POC consumes exact candidate SHA, production consumes promoted release. |
| Leopard Cat Tarot | `alston-personal/leopardcat-tarot` | historical `ops/leopardcat-runtime-inspect` and `chore/leopardcat-runtime-inspect` carrier branches plus Tarot-specific deploy/inspect/probe workflows | Product handoff is `alston-personal/leopardcat-tarot#44`. PR #41 is a product-owned read-only parity gate, but retirement also requires a product-owned write/deploy replacement (or thin caller of a generic governed Core deploy capability) and exact runtime/artifact evidence. |
| Character Blueprint | unresolved; `alston-personal/charactergenerator` explicitly rejected as a provenance match | PR #53 browser/deployer fix | Preserve PR #53 as migration source and do not merge it into Core. Assign/create the actual Character Blueprint canonical repo before migrating v0.4 behavior; do not overwrite the distinct `charactergenerator` product. |
| Model2IR | canonical repo not yet assigned/created | real standalone package under `libs/model2ir` across historical `feat/model2ir-*` / `fix/model2ir-*` branches; latest observed carrier is v0.9.1 | Freeze the `agentmanager` lineage as migration provenance. Assign/create a standalone canonical repository, then migrate package/tests/fixtures/history with parity; do not continue library implementation in Core. |

## Leopard Cat Tarot carrier inventory

The remaining Tarot residue has now been reduced from an unspecified file-level inventory to explicit historical carrier provenance:

- `ops/leopardcat-runtime-inspect` @ `141bbfe27b789c5803c9c5b469d76377debf7aeb` — manual-draw production verification carrier;
- `chore/leopardcat-runtime-inspect` @ `d51487149b5911333b0f0a5e5a8171fe1afba26e` — production frontend bundle build/verification carrier;
- Tarot-specific workflow surfaces observed in the carrier history include:
  - `.github/workflows/ops-leopardcat-ai-probe.yml`;
  - `.github/workflows/ops-leopardcat-runtime-deploy.yml`;
  - `.github/workflows/ops-leopardcat-runtime-inspect.yml`;
  - `.github/workflows/leopardcat-production-deploy.yml` (modified by the latest carrier commit).

The canonical product repository already owns product-side Oracle/runtime inspection and production AI probing. PR `alston-personal/leopardcat-tarot#41` adds a read-only `Production Parity Gate`. That is necessary evidence, but it is not sufficient to retire a write-capable production deploy carrier. Product issue `alston-personal/leopardcat-tarot#44` therefore owns the remaining deploy/parity handoff.

Core must not delete or merge these historical carriers into `core/integration`. They become retirement candidates only after #44 demonstrates a product-owned deployment path (or a thin product caller of a generic governed Core deploy surface), exact source/artifact identity, public/runtime parity, and persisted receipt/evidence.

## Character Blueprint negative provenance

The previous `alston-personal/charactergenerator` name candidate has been inspected and rejected as a canonical identity match for the known Character Blueprint artifact.

Known Character Blueprint migration source:

- PR #53 is a one-file product deployer fix for `scripts/deploy_character_blueprint_poc.py`;
- that deployer consumes `web_assets/character-blueprint-poc.html`;
- the source carries `character-blueprint-poc` / v0.4 markers, `character-blueprint-ir/v0.4`, an image → 3D proxy interaction, Three.js, and `OrbitControls`.

Observed `charactergenerator` product:

- `main` currently contains a single `index.html`;
- the UI describes image upload → AI-generated character text description and full-body imagery;
- no `OrbitControls` or `character-blueprint-ir` marker is present in repository code search.

This is sufficient to reject automatic identity inference. It is not authority to rename or repurpose `charactergenerator`; #118 instead keeps Character Blueprint unresolved until an explicit canonical repository is assigned or created. PR #53 remains frozen migration evidence and must not be merged into AgentOS Core.

## Model2IR carrier inventory

Model2IR already exists as an independently packaged library inside historical `agentmanager` branches. It must therefore be treated as a concrete migration, not a future placement rule.

Latest observed carrier:

- `feat/model2ir-meshy-weak-structure-v091` @ `1314bb01e718e1a930e24441b3544dd8da020065`;
- package root `libs/model2ir/` with `README.md`, `pyproject.toml`, and `src/`;
- package metadata declares `name = "model2ir"`, `version = "0.9.1"`, Python `>=3.10`, and a `model2ir` console script;
- README describes the reusable 3D asset → Canonical Character IR boundary extracted from AgentOS research, including reversible GLB/VRM handling, stabilization, teacher dataset support, and weak-structure profiling.

Observed branch lineage includes:

- `feat/model2ir-v01`;
- `feat/model2ir-reversible-v02`;
- `feat/model2ir-external-semantics-v03`;
- `feat/model2ir-stabilized-import-v04`;
- `feat/model2ir-real-family-stability-v05`;
- `feat/model2ir-vrm-topology-v06`;
- `feat/model2ir-teacher-dataset-v07` plus rebase variants;
- `feat/model2ir-library-v08` and `fix/model2ir-cli-v081`;
- `feat/model2ir-reversible-glb-v09`;
- `feat/model2ir-meshy-weak-structure-v091`.

The branch names are provenance, not canonical source authority. Preserve the latest accepted package state and relevant history until a standalone repository is assigned/created. Migration must reproduce package tests/fixtures and preserve the library contract before the old `agentmanager` carrier can be retired. New Model2IR implementation must not continue in Core merely because the current carrier is there.

## Legacy Core proposal separation

Open PRs #2, #17, #22, and #43 are Core proposals, not product migrations. They require accepted-delta extraction into focused `core/issue-*` work and must not be conflated with #118.

PR #18 is a generic social-capability candidate and should be reviewed as a capability boundary. PR #125 mixes generic social capability with Vendor ingestion and must be split before integration; Vendor-specific ingestion belongs in the Vendor repository.

## Retirement gate

A product-specific carrier in `agentmanager` may be closed/removed only when all applicable gates pass:

1. canonical product repository and Project Identity are explicit;
2. the product-owned source contains the accepted/newer implementation;
3. tests/CI are reproducible from that repository;
4. deployment/execution can be requested through a generic governed Core surface without embedding product logic in Core;
5. runtime/online parity is verified against an exact source SHA/artifact;
6. evidence is persisted;
7. only then is the old `agentmanager` product carrier marked retired/closed.

This means cleanup is intentionally incremental. Repository cleanliness must not be obtained by deleting the only working deployment path before its replacement exists.
