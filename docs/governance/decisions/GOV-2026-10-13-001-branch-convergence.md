# GOV-2026-10-13-001 — Single mainline and branch convergence

Status: PROPOSED; requires explicit human approval and constitutional governance checks before merging into protected `main`.

## Decision
- Treat `main` as the future canonical development integration branch.
- Treat `core/integration` as a temporary, explicitly bounded production/OIDC authority lane until measured cutover and rollback acceptance. Do not abruptly retire it.
- New functionality must not diverge onto both long-lived branches without declared owner, source SHA, target branch, effective-equivalence analysis, CI, and a reconciliation plan.
- Existing protected-branch approvals and immutable-release controller remain authoritative; this decision does not authorize merges or production mutations.
- Govern branch convergence in existing #1682, coordinated by #889; do not create duplicate migration controllers.

## Evidence checkpoint
GitHub compare main...core/integration on 2026-10-13: diverged; core/integration ahead by 3348, behind by 1443 historical commits; counts are NOT net unique feature changes. `main` governance/runtime_ownership labels core as partial whereas `core/integration` labels core active and points to past release receipt. Actual present Oracle deployment identity must be independently verified. Oracle direct Runner service was observed failed OOM with Restart=no; capacity recovery and governance gate are separate prerequisites. Existing Atlas PR #1769 and wardrobe #69 illustrate consumer impact.

## Migration plan / no-regret gates
1. Freeze uncontrolled parallel feature development via review policy; log exceptions for production hotfixes and ensure backport/forward-port receipts.
2. Record pinned SHAs, full untruncated file inventory, effective feature equivalence categories, owners, secret-safe evidence, production service consumers and OIDC subject/issuer allowlists. Never classify by commit count alone.
3. Migrate in small reviewed slices with tests and provenance; no bulk giant merge, force push, reset, mutable production checkout or unreviewed cherry-pick.
4. Revalidate Runner governance, ONE, Supervisor, Dashboard, Studio consumers, Node/Executor and receipts under immutable releases. Establish OIDC cutover and independent rollback; existing core/integration stays in service until live receipt proves main's authority.
5. Only then declare one mainline and deprecate core/integration; closure demands executable CI, live attestation, before/after authoritative inventory, and human approval.

## Failure and rollback
Any missing equivalence, failed authority negotiation, missing live receipt or consumer regression retains original production owner, marks migration BLOCKED with next action and owner, and rolls back via governed immutable release. An apparently mergeable PR or CI success is not runtime proof.

## Constitutional governance
Proposal changes `.agent/CONSTITUTION.yaml`, requiring explicit decision record, migration note, drift tests PASS, and explicit human approval to merge into protected main.
