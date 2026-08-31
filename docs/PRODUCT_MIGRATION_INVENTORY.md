# Product Migration Inventory

Status: Issue #118 migration phase 2, 2026-08-31

This document classifies non-Core work that still appears in `alston-personal/agentmanager`. It does not authorize destructive cleanup. A carrier or historical branch is retired only after a canonical product-owned replacement exists and runtime/deployment parity has been verified.

## Current classifications

| Product / scope | Canonical repo | Agentmanager residue | Current decision |
| --- | --- | --- | --- |
| Vendor Reputation | `alston-personal/vendor-reputation-service` | PR #97 patrol artifact carrier, #99 calibration carrier, #127 monitored-source scheduler | Keep temporarily. Product implementation is already outside Core, but Oracle execution/scheduling carriers still depend on Core infrastructure. Migrate after a governed product-owned runner/capability path is verified. |
| ArcanaForge | `alston-personal/arcanaforge` | PR #136 POC release carrier | Keep until #66 provides a governed static-release path and an exact ArcanaForge source/artifact receipt can drive `/poc/arcanaforge/`. |
| LayoutLib | `alston-personal/layoutlib` | Core-side deploy/governance residue tracked by #96 | Keep only generic deployment/promotion adapter. Layout implementation and product tests stay in `layoutlib`; POC consumes exact candidate SHA, production consumes promoted release. |
| Leopard Cat Tarot | `alston-personal/leopardcat-tarot` | remaining residue still requires file-level inventory | Product repo already has PR #41 implementing a production parity gate. This is the preferred ownership pattern: product-specific parity checks stay with the product. |
| Character Blueprint | unresolved; `alston-personal/charactergenerator` is only a candidate | PR #53 browser/deployer fix | Preserve, do not merge into Core. First establish explicit Project Identity and canonical repo, then migrate with parity evidence. |
| Model2IR | unresolved | future risk of implementation landing in Core | Do not add new Model2IR implementation to `agentmanager`; assign/create a canonical library repo first. |

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
