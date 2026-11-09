# Project → Repository / Environment Map

Status: Issue #118 inventory, 2026-08-31

This document separates **Project Identity**, **repository ownership**, **development branch**, and **online environment**. A branch name is never deployment authority by itself.

## Canonical rules

- `main` means accepted/promotion source state. Active agents do not directly develop on `main`.
- Feature/fix branches are mutable development candidates.
- A `develop`/integration branch is optional. Use it when a project needs a shared integration/POC lane.
- POC/staging may deploy an exact candidate SHA from feature/develop.
- Production deploys an exact accepted SHA/tag/release from `main` or a promoted release artifact.
- Every deployment must persist environment + repository + source ref + exact SHA/artifact identity.
- Project identity is explicit; it is not inferred from repository path.

## Current inventory

| Project | Canonical repository | Development lane | Main meaning | Online/deploy state | Repo-boundary status |
| --- | --- | --- | --- | --- | --- |
| AgentOS Core | `alston-personal/agentmanager` | `core/issue-*` → `core/integration` | protected publication history | live Core uses deployment generation + exact accepted SHA, not branch head | canonical Core owner |
| Vendor Reputation Service | `alston-personal/vendor-reputation-service` | product feature/fix lane; integration policy to be normalized | accepted Vendor source | shared Oracle runner blocker #130 is resolved; remaining migration is Vendor-owned governed scheduling/execution with exact Vendor source identity and receipt/runtime parity | canonical repo confirmed; carrier retirement tracked by Vendor #27 |
| LayoutLib / Layout Lab | `alston-personal/layoutlib` | `feature/*` / `fix/*` → `develop` | accepted/promoted Layout source | generic release-lane authority is canonical in `core/integration` via #158; POC still needs one live exact-`develop`-candidate dispatch/receipt acceptance under #96 | canonical repo confirmed; product work unblocked, live POC acceptance pending |
| ArcanaForge | `alston-personal/arcanaforge` | product feature/fix lane; integration policy to be normalized | accepted ArcanaForge source | Core static-release blocker #66 is resolved; remaining gate is to make `/poc/arcanaforge/` receipt identify the exact canonical `arcanaforge` source/artifact rather than only the `studio-web` host-adapter SHA | canonical repo confirmed; product provenance retirement gate tracked by ArcanaForge #3 |
| Leopard Cat Tarot | `alston-personal/leopardcat-tarot` | product feature/fix lane; integration policy to be normalized | accepted Tarot source | production/POC source mapping still requires product-owned write/deploy replacement plus exact deployment receipt evidence | canonical repo confirmed; carrier retirement tracked by Tarot #44 |
| Character Blueprint | unresolved; `alston-personal/charactergenerator` has been checked and rejected as a canonical identity match | unresolved | unresolved | existing Character Blueprint material in `agentmanager` must not be treated as Core authority or migrated into `charactergenerator` by name similarity | canonical repository NOT yet assigned; explicit create/assignment decision required |
| Model2IR | canonical repository unassigned; no `alston-personal/model2ir` repository exists in current inventory | historical `feat/model2ir-*` / `fix/model2ir-*` work in `agentmanager` is a migration carrier, not an approved Core development lane | new repository `main` must become accepted library source after migration | library boundary; no production web environment required by default | actual standalone v0.9.1 library carrier identified in `agentmanager`; repo creation/assignment is now the blocking identity step |

## Dependency-state rule

A shared Core dependency and a product-carrier retirement gate are different state dimensions.

- A resolved infrastructure/capability issue must not remain an active project blocker merely because the product still has a historical carrier to migrate.
- Vendor Core #130 is completed: the Oracle-labelled self-hosted runner successfully claimed and completed the formerly queued Vendor governance audit. Vendor #27 now owns the remaining product execution/scheduling migration.
- ArcanaForge Core #66 is completed: governed fenced static release exists. ArcanaForge #3 now owns the remaining product source/artifact provenance gate for #136 retirement.
- LayoutLib #96 is split: generic release-lane authority is accepted in `core/integration` through PR #158; only live exact-candidate POC dispatch, receipt/public parity, and subsequent carrier retirement remain.

This distinction is machine-readable in `governance/product-migrations.json`. Workers block only on the precise unresolved step, not on the historical issue number as a blanket project lock.

## Character Blueprint identity evidence

`alston-personal/charactergenerator` is no longer an unresolved name candidate. It has been inspected and does not match the known Character Blueprint product provenance:

- frozen migration source PR #53 changes `scripts/deploy_character_blueprint_poc.py` and deploys `web_assets/character-blueprint-poc.html`;
- the Character Blueprint source identifies `data-app="character-blueprint-poc"`, version `0.4.0`, schema `character-blueprint-ir/v0.4`, a browser-local image → 3D proxy flow, Three.js, and `OrbitControls`;
- `alston-personal/charactergenerator` `main` currently contains a single `index.html` whose UI describes image upload → AI text description / full-body image generation;
- repository code search finds neither `OrbitControls` nor `character-blueprint-ir` in `charactergenerator`.

Therefore similar naming is contradicted by product behavior and source markers. Core must not overwrite or repurpose `charactergenerator` as the Character Blueprint canonical repository without a separate explicit product-consolidation decision. For #118, Character Blueprint remains identity-unresolved and requires assignment/creation of its canonical repository before PR #53 behavior is migrated.

## Model2IR carrier evidence

Model2IR is no longer classified as merely a future independent-library direction. A real standalone package already exists on historical non-Core branches inside `agentmanager`.

Latest observed carrier:

- branch: `feat/model2ir-meshy-weak-structure-v091`;
- tip: `1314bb01e718e1a930e24441b3544dd8da020065`;
- package root: `libs/model2ir/`;
- `pyproject.toml`: project `model2ir`, version `0.9.1`, console script `model2ir`;
- README explicitly defines the reusable **3D asset → Canonical Character IR** boundary as extracted from the AgentOS research codebase.

Observed lineage in `agentmanager` includes `feat/model2ir-v01`, reversible v0.2, external semantics v0.3, stabilized import v0.4, real-family stability v0.5, VRM topology v0.6, teacher-dataset v0.7 variants, library v0.8 / CLI v0.8.1, reversible GLB v0.9, and Meshy weak-structure v0.9.1.

This lineage is migration provenance, not permission to keep developing the library inside Core. #118 must preserve the v0.9.1 carrier until a canonical standalone repository is assigned/created and the package, tests, fixtures, and relevant history are migrated with parity. After that migration, new Model2IR work belongs in the product/library repository.

## `agentmanager` ownership boundary

`agentmanager` retains only:
- AgentOS Core runtime/control plane;
- ONE / Realm;
- Node runtime and generic node protocols;
- governance / authority / receipts / canonical state;
- generic capability contracts and cross-repository integration protocols.

Product-specific UI, datasets, product workflows, deployers, release scripts, browser tests, benchmarks, and product implementation belong to each product repository.

A product may depend on a generic Core capability, but that dependency does not transfer the product implementation into `agentmanager`.

## Environment identity

A deployment receipt should have at least:

```json
{
  "project_id": "layoutlib",
  "repository": "alston-personal/layoutlib",
  "environment": "poc",
  "source_ref": "develop",
  "source_sha": "<exact sha>",
  "artifact_digest": "<digest if applicable>",
  "deployed_at": "<timestamp>"
}
```

This answers the otherwise ambiguous question "is online using main or a branch?": the environment records both its semantic role and exact deployed source. Production is not defined merely by tracking `main`, and POC is not authoritative merely because a branch is online.

## Migration gate

For each non-Core product currently represented in `agentmanager`:
1. identify the canonical product repository;
2. compare provenance and accepted/current implementation;
3. reproduce tests/CI/deploy from the product repository;
4. verify the target online environment with an exact source receipt;
5. persist migration evidence;
6. remove product-specific implementation from a Core issue branch only after parity;
7. retain only generic contracts/integration adapters in Core.

Historical product branches are preserved until their unique accepted work is accounted for. No destructive cleanup and no protected-main mutation is implied by this inventory.
