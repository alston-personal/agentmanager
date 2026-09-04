# Product Employee Operating Acceptance

Status: **contract candidate; live operating acceptance not yet proven**

Issue: #238

## Purpose

Zeus Writer and YouTube AI Manager are the first production product Employees after the Core Spec Steward acceptance path. Their durable Employee identity must survive executor/model/session turnover and must be reconciled by the persistent Core Supervisor without requiring the Human to repeatedly say `繼續`.

## Current source slice

The #238 contract slice provides:

- active role contracts `product.zeus_writer` and `product.youtube_ai_manager`;
- bounded intent-only skills `writing.project.continue` and `youtube.optimization.scan`;
- idempotent Employee bootstrap contracts for both initial assignments;
- static role/skill/bootstrap consistency checks.

This source slice does **not** grant product execution authority and does not emit either live VERIFIED marker.

## Worker Host boundary

The current shared Employee Worker Host is intentionally allowlisted and currently implements only `spec_steward_o3`. Product Employees must not be registered by lying about their runner kind or by introducing module/argv/shell fields into the adapter registry.

The next execution slice must extend the shared host with fixed source-controlled runner kinds while preserving these invariants:

1. `runner_kind` is an enum selected by Core source, not an executable/module/argv string.
2. Each runner maps to one fixed bounded CLI surface in source code.
3. Child environment remains credential-isolated and allowlisted.
4. A product worker must re-check the exact governed Supervisor/S4 wake before Employee claim.
5. Child result schemas are allowlisted per runner kind and are sanitized before persistence.
6. Unknown runner kinds, result schemas, Employee/assignment/wake mismatches, or lease-generation mismatches fail closed.
7. GitHub Actions availability is never a control-plane fallback.

## Zeus Writer execution stages

### Z0 — contract

Machine-hydratable Employee, role, skill, assignment. No product side effect.

### Z1 — bounded read/checkpoint

A fixed Zeus worker may inspect only the explicitly configured canonical `zeus-writer` product root and durable assignment state, then persist a sanitized writing checkpoint. It must reject legacy Pulse/STATUS/possession state as authority.

### Z2 — writing candidate

A real executor produces one bounded continuation candidate for the selected writing project. Candidate creation is not protected-branch publication authority.

### Z3 — accepted source / downstream publication

Only separately authorized source acceptance may persist the new chapter in the product repository. The existing `publish_to_n8n` workflow remains downstream and reacts naturally to accepted chapter source.

Success marker `ZEUS_WRITER_PERSISTENT_EMPLOYEE=VERIFIED` additionally requires restart/resume continuity and terminal/checkpoint receipts.

## YouTube AI Manager execution stages

### Y0 — contract

Machine-hydratable Employee, role, skill, assignment. No external API access.

### Y1 — bounded local/read-only scan

A fixed worker performs a credential-free scan over explicitly authorized local/canonical inputs and persists optimization candidates.

### Y2 — governed live channel read

A separately authorized capability may obtain current YouTube channel/video state. Read authority must not imply mutation authority.

### Y3 — external metadata mutation

Title/description/subtitle/playlist writes require an explicit product capability authority and sanitized receipt. Employee role identity alone never grants this authority.

Success marker `YOUTUBE_AI_MANAGER_PERSISTENT_EMPLOYEE=VERIFIED` requires at least a real Y2 scan, Supervisor wake without Human `繼續`, executor claim, restart/resume continuity, and sanitized receipts. Y3 is not required for liveness proof.

## Repository boundaries

- Zeus Writer canonical product source: `alston-personal/zeus-writer`.
- YouTube AI Manager canonical product source: `alston-personal/youtube-ai-manager`.
- OmniRealm / Studio / LayoutLib / ArcanaForge are not Zeus Writer responsibilities; #213 owns residual carrier cleanup.

## Truth rule

`role registered` != `Employee running` != `product work executed` != `external side effect accepted`.

Each transition requires its own evidence and receipt.
