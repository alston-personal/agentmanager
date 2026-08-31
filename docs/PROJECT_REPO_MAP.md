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
| Vendor Reputation Service | `alston-personal/vendor-reputation-service` | product feature/fix lane; integration policy to be normalized | accepted Vendor source | Oracle/project carriers must consume pinned Vendor SHA; Vendor implementation should not live in `agentmanager` | canonical repo confirmed; migration cleanup pending |
| LayoutLib / Layout Lab | `alston-personal/layoutlib` | `feature/*` / `fix/*` → `develop` | accepted/promoted Layout source | POC may consume exact `develop` candidate SHA; production remains promoted/release state | canonical repo confirmed; #96 governs lane/deploy boundary |
| ArcanaForge | `alston-personal/arcanaforge` | product feature/fix lane; integration policy to be normalized | accepted ArcanaForge source | `/poc/arcanaforge/` is POC and must deploy a pinned candidate through governed static-release capability | canonical repo confirmed; #66 blocks only POC release step |
| Leopard Cat Tarot | `alston-personal/leopardcat-tarot` | product feature/fix lane; integration policy to be normalized | accepted Tarot source | production/POC source mapping still requires explicit deployment receipt inventory | canonical repo confirmed; remove any product implementation/carriers from Core after parity evidence |
| Character Blueprint | unresolved; `alston-personal/charactergenerator` is a repository-name candidate only | unresolved | unresolved | existing Character Blueprint material in `agentmanager` must not be treated as Core authority | canonical repository NOT yet verified; do not infer from similar name |
| Model2IR | unresolved; no `alston-personal` repository named `model2ir` found in current repository search | unresolved | unresolved | new independent-library direction requires explicit canonical repository assignment | repository unresolved; do not place implementation in Core by default |

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
