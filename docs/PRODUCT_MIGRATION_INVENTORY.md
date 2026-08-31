# Product Migration Inventory

Status: Issue #118 phase 2 inventory, 2026-08-31

Purpose: identify product-owned material still represented in `alston-personal/agentmanager` so Core can stop acting as a catch-all product/deployment repository. This document classifies current open PRs by ownership; it does not delete history or claim migration parity.

## Classification rules

- **CORE**: generic AgentOS runtime, ONE/Realm, Node protocols, governance/authority, canonical state, receipts, generic capability contracts.
- **PRODUCT**: product-specific implementation, UI, data, product deployers/workflows, release scripts, product benchmarks.
- **MIXED**: contains both reusable Core capability/runtime work and product-specific adapters/ingestion; must be split before integration.
- Product-owned work must not be merged into `agentmanager` merely because Oracle currently executes its carrier.
- Oracle execution/deployment authority is a Core concern; the workload definition/source remains product-owned.

## Open PR inventory

| PR | Observed changed files | Classification | Migration disposition |
| --- | --- | --- | --- |
| #127 Vendor monitored source sync | `.github/workflows/oracle-register-vendor-threads-source.yml`, `.github/workflows/oracle-sync-vendor-monitored-sources.yml`, `scripts/run_vendor_monitored_source_sync.sh` | PRODUCT | Freeze as migration source. Vendor workload/schedule belongs to `alston-personal/vendor-reputation-service`; Core should expose only the governed execution/deployment primitive needed to run it. |
| #99 Vendor Threads calibration | `.github/workflows/oracle-vendor-threads-calibration.yml`, `scripts/run_vendor_threads_calibration.sh` | PRODUCT | Freeze as migration source. Calibration workflow belongs to Vendor repo; Core provides generic Oracle execution boundary only. |
| #97 Vendor patrol receipt carrier | `.github/workflows/oracle-register-vendor-threads-source.yml` | PRODUCT | Freeze as migration source. Evidence publication policy may inform generic Core receipts, but this workflow is Vendor-specific. |
| #136 ArcanaForge POC release | `.github/workflows/oracle-release-arcanaforge-poc.yml` | PRODUCT/CARRIER | Freeze as migration source. Arcana release intent/source belongs to Arcana/Studio source repo; generic fenced static-release authority belongs to Core #66. |
| #53 Character Blueprint browser deployer | `scripts/deploy_character_blueprint_poc.py` | PRODUCT | Freeze as migration source until canonical Character Blueprint repo is verified. Do not integrate into Core. |
| #125 Social capability + Vendor ingestion | generic social capability/governance files plus `agentos_node/social/vendor_ingest.py` and `tests/test_vendor_threads_ingest.py` | MIXED | Split. Generic social capability can be extracted to focused Core issue branch; Vendor ingestion adapter/tests belong to Vendor repo. Do not merge mixed PR as-is. |

## Current canonical repositories

- Vendor Reputation Service: `alston-personal/vendor-reputation-service`
- LayoutLib / Layout Lab: `alston-personal/layoutlib`
- ArcanaForge: `alston-personal/arcanaforge`
- Leopard Cat Tarot: `alston-personal/leopardcat-tarot`
- Character Blueprint: unresolved; `alston-personal/charactergenerator` is only a naming candidate and is not accepted as authority without provenance verification.
- Model2IR: unresolved; no same-name canonical repository established yet.

## Required migration pattern

For a product-specific Oracle workflow currently living in `agentmanager`:

1. preserve the current PR/branch as historical migration source;
2. move workload definition, product script, schedule intent, tests and product-specific evidence policy to the canonical product repo;
3. if the product repo cannot directly reach Oracle, depend on a generic Core capability rather than copying product workflow into Core;
4. Core capability accepts a bounded artifact/request and returns a governed receipt;
5. verify parity against the historical carrier;
6. only then close the legacy `agentmanager` PR as superseded;
7. do not delete historical branch/evidence until provenance is accounted for.

## Mixed PR #125 split boundary

Keep/extract to Core only if independently justified and tested:
- generic social capability contracts;
- credential-reference boundary and secret-free receipts;
- generic Threads/Facebook/Instagram executor implementation;
- generic capability governance and write-approval gates;
- generic social capability documentation/tests.

Move out of Core:
- `agentos_node/social/vendor_ingest.py`;
- `tests/test_vendor_threads_ingest.py`;
- any Vendor-specific workflow, query semantics, schema mapping, DB ingestion, calibration or patrol behavior.

The extraction must be based on actual accepted deltas, not a blind merge of #125.

## Non-blocking rule

Migration work does not globally pause the product. Only steps requiring a missing Core capability remain blocked. Product feature development continues in its canonical repository.

## Exit criteria for #118 phase 2

- every open product-owned/mixed `agentmanager` PR is classified;
- product PRs are explicitly frozen from Core integration pending migration parity;
- migration issues exist in canonical product repos where the repository is known;
- mixed PRs have an explicit split boundary;
- no protected `main` publication is implied by this inventory.
