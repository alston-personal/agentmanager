# Product Migration Inventory

Status: Issue #118 migration phase 2, 2026-08-31

This document classifies non-Core work that still appears in `alston-personal/agentmanager`. It does not authorize destructive cleanup. A carrier or historical branch is retired only after a canonical product-owned replacement exists and runtime/deployment parity has been verified.

## Current classifications

| Product / scope | Canonical repo | Agentmanager residue | Current decision |
| --- | --- | --- | --- |
| Vendor Reputation | `alston-personal/vendor-reputation-service` | PR #97 patrol artifact carrier, #99 calibration carrier, #127 monitored-source scheduler | Keep temporarily as migration sources; do not merge into Core. Vendor migration is tracked by `vendor-reputation-service#26`. Product implementation/workload/schedule belongs to Vendor; Core should expose only a governed Oracle execution primitive. |
| ArcanaForge | `alston-personal/arcanaforge` | PR #136 POC release carrier | Keep as migration source until #66 provides a governed static-release path and an exact ArcanaForge source/artifact receipt can drive `/poc/arcanaforge/`. Product migration is tracked by `arcanaforge#2`. |
| LayoutLib | `alston-personal/layoutlib` | Core-side deploy/governance residue tracked by #96 | Keep only generic deployment/promotion adapter. Layout implementation and product tests stay in `layoutlib`; POC consumes exact candidate SHA, production consumes promoted release. |
| Leopard Cat Tarot | `alston-personal/leopardcat-tarot` | remaining residue still requires file-level inventory | Product repo already has PR #41 implementing a production parity gate. This is the preferred ownership pattern: product-specific parity checks stay with the product. |
| Character Blueprint | unresolved; `alston-personal/charactergenerator` is only a candidate | PR #53 browser/deployer fix | Preserve as migration source and do not merge into Core. First establish explicit Project Identity and canonical repo, then migrate with parity evidence. |
| Model2IR | unresolved | future risk of implementation landing in Core | Do not add new Model2IR implementation to `agentmanager`; assign/create a canonical library repo first. |

## File-level evidence from current open PRs

The ownership classification above is based on actual changed-file inventories, not PR titles alone:

- PR #127 changes only `.github/workflows/oracle-register-vendor-threads-source.yml`, `.github/workflows/oracle-sync-vendor-monitored-sources.yml`, and `scripts/run_vendor_monitored_source_sync.sh`. Classification: **PRODUCT carrier**.
- PR #99 changes only `.github/workflows/oracle-vendor-threads-calibration.yml` and `scripts/run_vendor_threads_calibration.sh`. Classification: **PRODUCT carrier**.
- PR #97 changes only `.github/workflows/oracle-register-vendor-threads-source.yml`. Classification: **PRODUCT carrier**.
- PR #136 changes only `.github/workflows/oracle-release-arcanaforge-poc.yml`. Classification: **PRODUCT-specific release carrier**; generic static-release authority belongs to Core #66.
- PR #53 changes only `scripts/deploy_character_blueprint_poc.py`. Classification: **PRODUCT deployer**.
- PR #125 changes generic social capability/runtime/governance files together with `agentos_node/social/vendor_ingest.py` and `tests/test_vendor_threads_ingest.py`. Classification: **MIXED**; it must be split before integration.

Each of #97, #99, #127, #136, #53, and #125 now has an explicit freeze/migration comment. Freeze means no direct merge into `agentmanager`; it does not mean the historical branch/evidence may be deleted.

## Mixed PR #125 split boundary

PR #125 must not be merged as-is. Core issue #144 owns extraction of the independently justified generic capability delta.

Candidate Core-owned scope:
- generic social capability contracts;
- credential-reference boundary and secret-free receipts;
- generic Threads/Facebook/Instagram executor behavior;
- generic capability governance and write-approval gates;
- generic social capability documentation/tests.

Vendor-owned scope, tracked by `vendor-reputation-service#26`:
- `agentos_node/social/vendor_ingest.py`;
- `tests/test_vendor_threads_ingest.py`;
- Vendor-specific ingestion/schema/database/query/calibration/patrol semantics;
- Vendor-specific Oracle workflows.

The extraction must be based on actual accepted deltas from current `core/integration`, not a blind merge of #125.

## Legacy Core proposal separation

Open PRs #2, #17, #22, and #43 are Core proposals, not product migrations. They require accepted-delta extraction into focused `core/issue-*` work and must not be conflated with #118.

PR #18 is a generic social-capability candidate and should be reviewed as a capability boundary. PR #125 is the mixed successor/candidate described above and remains frozen until #144 and Vendor migration account for both ownership domains.

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

## Non-blocking rule

Migration does not globally pause a product. Only the exact step requiring an unavailable Core capability is blocked. Vendor, ArcanaForge, LayoutLib, Tarot and other product feature work continues in the canonical product repository while their migration/deployment dependencies are resolved.
