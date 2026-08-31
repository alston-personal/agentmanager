# Project Release-Lane Authority

Status: Core #96 accepted-delta extraction for `core/integration`, 2026-08-31

Project identity does not imply branch-mutation, promotion, or deployment authority. AgentOS Core treats development, promotion, POC deployment, and production deployment as distinct governed actions.

## Canonical policy source

`governance/project-release-lanes.json` is the single machine-readable authority source for release lanes. Evaluators and CI read this file; they must not maintain a second hard-coded copy of project policy.

The registry records, per project:

- canonical repository;
- allowed development branch patterns;
- promotion branch and required approval boundary;
- POC and production source branches;
- exact-source-SHA requirements;
- environment surfaces and immutable release boundaries;
- authority owners and invariants.

## Enforcement

`scripts/check_project_release_lane.py` denies unknown projects/actions and enforces the registry.

For the current LayoutLib entry:

- development writes are allowed on `develop`, `feature/*`, `fix/*`, and `governance/*`;
- development writes to `main` are denied;
- promotion to `main` requires an explicit human approval event;
- POC deployment requires source branch `develop` **and** an exact 40-character source SHA;
- production deployment requires source branch `main` **and** an exact 40-character source SHA;
- immutable `release/v0.7.9` remains provenance and is not rewritten by the v0.8 POC lane.

`.github/workflows/project-release-lane-guard.yml` runs regression and CLI acceptance probes for changes targeting either `core/integration` or `main`.

## Separation from product deployment carriers

This contract intentionally does **not** copy `.github/workflows/oracle-release-layoutlab-v08-dev.yml` from the historical/main #131 carrier into `core/integration`.

The generic Core authority says whether a project/environment/source identity is permitted. Product-specific build/copy/HTML acceptance logic remains a migration carrier until a product-owned release request can invoke a generic governed deployment surface and produce a receipt containing at least:

`project + environment + repo + source_ref + exact SHA + artifact`.

Therefore accepting this Core authority contract does not by itself retire Layout-specific deployment residue. #96 remains open until an exact LayoutLib `develop` candidate is actually deployed through the governed path and public/receipt parity is demonstrated.

## Provenance

The accepted behavior was first proven on historical PR #129 and extended by #131. This integration extraction deliberately removes the earlier dual-authority design in which policy existed both in YAML and a hard-coded Python `POLICIES` table. Historical branches/PRs remain evidence; `core/integration` is the canonical integration target for the cleaned Core contract.
