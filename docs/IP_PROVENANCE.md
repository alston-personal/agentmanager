# AgentOS IP Provenance & Employment Boundary

## Purpose

AgentOS is managed as a personal pre-existing / independently developed platform. This document establishes provenance and separation controls so that later use in employment-related work does not silently collapse AgentOS Core, reusable capabilities, or generic platform infrastructure into a company-specific deliverable.

This is a governance control, not a legal conclusion. Employment agreements and applicable law remain authoritative.

## Canonical boundary

Treat these as **AgentOS Core / reusable platform IP** unless an explicit signed agreement states otherwise:

- Realm / Node protocols and onboarding
- Scheduler, routing, capability, receipt, IR/continuation, governance and orchestration architecture
- reusable cross-project capabilities and generic adapters
- generic web/AI/crawler/runtime infrastructure
- personal project registries, schemas, architecture, documentation and tests

Treat company-specific outputs as a separate delivery lane:

- company-specific business rules
- company confidential information
- company/customer data
- internal credentials, infrastructure details or proprietary datasets
- code written specifically as a company deliverable under the employment scope

Company-specific work should consume AgentOS through a plugin, adapter, connector, project repository or capability contract. It must not become the source of truth for AgentOS Core.

## Required classification

Every material Core or reusable capability change should be classifiable as one of:

- `personal-preexisting` — existed before the relevant company use case or employment scope.
- `personal-independent` — independently created outside the company deliverable scope using personal resources.
- `company-deliverable` — created specifically as a company work product.
- `mixed-review-required` — provenance or scope is mixed/uncertain and must not be promoted into Core until reviewed.

For material changes, preserve:

- repository and exact commit
- project/capability ID
- author/executor
- resource origin
- employment-scope classification
- third-party inputs and licenses
- supporting design/IR/provenance evidence

## Resource separation

For AgentOS Core, prefer personal ownership/control for:

- GitHub/repository
- cloud/VM/storage
- domains and DNS
- AI subscriptions/API accounts
- development hardware
- payment records

Do not persist company confidential material, credentials, proprietary source code or customer data into AgentOS repositories, durable memory, datasets or reusable capabilities.

Use of a company device, office location or work-related use case must never be treated by an Agent as sufficient evidence of ownership in either direction. Escalate mixed provenance instead of guessing.

## Promotion guard

A change classified `mixed-review-required` must not be promoted into canonical AgentOS Core until the boundary is resolved.

A `company-deliverable` must remain in a company/project-specific lane unless there is explicit authorization and IP review to extract a generic, independently implementable capability.

Third-party code must retain license/source provenance.

## Evidence package

Maintain, where available:

1. Git commit and repository creation history.
2. Canonical IR and architecture history.
3. Personal domain/cloud/subscription/payment evidence.
4. Release receipts and exact source SHAs.
5. Pre-existing IP / side-project exclusion agreement with the employer.
6. Written records of any disputed or mixed-scope feature before promotion.

## Employment agreement review

Review employment agreement, NDA, employee handbook and IP-assignment language for:

- employee inventions
- works made in the course of duties
- side projects
- use of employer resources
- related-business / conflict-of-interest clauses
- confidentiality and trade-secret obligations

Where practical, obtain a written pre-existing-IP / side-project exclusion identifying AgentOS and its repositories/platform architecture.

For patentable inventions or other high-value IP, obtain Taiwan-qualified IP/legal advice before relying on an internal classification alone.

## Agent behavior

Agents working on AgentOS must:

1. discover this policy before promoting reusable Core changes;
2. preserve provenance rather than overwrite it;
3. keep company-specific delivery separate from Core;
4. fail closed on mixed or confidential provenance;
5. never assert that AgentOS ownership has been legally resolved without documentary/legal authority.

Canonical machine-readable policy: `governance/ip-ownership-policy.json`.
