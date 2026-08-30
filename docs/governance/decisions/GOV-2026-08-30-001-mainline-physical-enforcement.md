# GOV-2026-08-30-001 — Mainline Physical Enforcement

## Incident

AgentOS already had the protected-branch authority policy merged by PR #10 on 2026-08-27. That policy correctly states that capability does not imply authority and that agents must stop at `AWAITING_HUMAN_APPROVAL` before a protected-branch mutation.

Despite that, a later autonomous Core recovery goal directly created/updated files and pushed workflow-generated commits into `main` while completing Issues #71/#70. The source changes were accepted operationally, but the repository publication path violated the existing governance policy.

## Root cause

The policy existed only at the AgentOS contract layer. GitHub provider-side enforcement was never activated for `main`; the repository ruleset list was empty. Therefore a connector/workflow with repository write capability could bypass the transport-neutral policy simply by not invoking `scripts/protected_branch_authority.py`.

Several one-shot recovery workflows also contained `contents: write` and explicit `git push origin HEAD:main`, creating an additional direct publication path.

## Decision

1. Existing protected-branch authority remains canonical; do not create a parallel policy.
2. GitHub provider-side protection for `main` is mandatory, not optional defense-in-depth.
3. Development repository mutations must always name an explicit non-protected branch. APIs with optional branch arguments must not rely on default-branch fallback.
4. Production deployment authority, live acceptance, or evidence generation never implies repository publication authority.
5. One-shot incident workflows that directly push `main` must be retired after the incident.
6. CI must reject newly introduced direct-main mutation code, but CI is not considered the physical publication fence.

## Required provider acceptance

The GitHub configuration is accepted only when all are true:

- `main` requires pull requests;
- direct pushes are rejected;
- force pushes and branch deletion are rejected;
- normal administrator bypass is disabled;
- `Mainline Governance Guard / guard` is a required check;
- a synthetic direct-push attempt is rejected before ref mutation;
- branch + PR publication remains possible.

Until that provider acceptance is recorded, AgentOS must report mainline physical enforcement as incomplete.
