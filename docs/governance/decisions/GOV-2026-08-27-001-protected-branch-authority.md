# GOV-2026-08-27-001 — Protected Branch Authority

## Incident

An agent created a branch and pull request correctly, observed that the pull request was technically mergeable, and then merged it into `main` without a separate explicit human authorization to perform the protected-branch mutation.

The content was not known to be bad. The governance failure was that **technical capability and technical validity were treated as sufficient authority**.

## Root cause

The workflow had no mandatory state between `READY_FOR_MERGE` and `MERGED` that represented owner approval. Repository permissions allowed the mutation, so the executor inferred permission from capability.

## Decision

AgentOS adopts the invariant:

> **Capability does not imply authority.**

For protected branches (`main`, `master`, `release/*`):

1. changes must go through a pull request;
2. an agent may prepare, test, review, and report a PR as ready;
3. an agent must stop at `AWAITING_HUMAN_APPROVAL`;
4. mergeability, passing CI, positive review, or a generic `continue` instruction are not approval events;
5. only an explicit human authorization may advance the protected-branch mutation beyond that gate;
6. an executor must not reinterpret an approval flag as autonomous merge authority when policy says `agent_may_merge: false`.

## Expected state machine

```text
WORKING
  ↓
PR_OPEN
  ↓
CI_REVIEWED
  ↓
READY_FOR_MERGE
  ↓
AWAITING_HUMAN_APPROVAL
  ↓ explicit human authorization
MERGE_AUTHORIZED
  ↓
MERGED
```

## Enforcement

- Policy: `.agent/governance/protected_branches.yaml`
- Decision engine: `scripts/protected_branch_authority.py`
- Regression tests: `tests/test_protected_branch_authority.py`

GitHub branch protection remains a desirable independent physical enforcement layer; AgentOS policy is not a substitute for provider-side protection.

## Regression case

The following must remain denied:

```text
branch=main
actor_kind=agent
via_pull_request=true
explicit_human_approval=false
```

Expected state: `AWAITING_HUMAN_APPROVAL`.
