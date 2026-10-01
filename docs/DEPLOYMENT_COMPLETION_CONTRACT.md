# Deployment Completion Contract

## Purpose

Prevent AgentOS from confusing source publication, CI success, build success, or a
deployment attempt with a completed user-visible change.

## Completion states

Every change that has a runtime or public surface MUST be classified as exactly one
of these states:

- `SOURCE_READY`: source exists in the canonical repository.
- `CI_VERIFIED`: automated build/tests passed.
- `DEPLOY_QUEUED`: a deployment request exists but has not executed.
- `DEPLOY_FAILED`: deployment executed and failed or side effects are unknown.
- `DEPLOYED_UNVERIFIED`: runtime mutation succeeded but target acceptance has not passed.
- `PRODUCTION_VERIFIED`: target acceptance passed against the actual production surface.

Only `PRODUCTION_VERIFIED` may be reported as "done", "fixed", "live", "available",
or equivalent when the user requested a deployed/runtime/public outcome.

## Required evidence

A production completion claim requires all of:

1. exact source revision,
2. deployment carrier/action identity,
3. execution receipt with successful side effect,
4. target-specific acceptance against the production URL/service/runtime,
5. rollback or repair path for mutable deployments.

CI success alone is never deployment evidence.

## Web acceptance

For public web routes, acceptance MUST verify the requested route/content itself.
A generic HTTP 200 is insufficient when the web server has SPA/index fallbacks.

Examples:

- verify route-specific marker/title/schema,
- verify expected JSON shape for data endpoints,
- detect when requested route body is identical to the site home fallback,
- record the final public URL and exact deployed revision.

## Failure handling

If deploy or acceptance fails:

- keep project/change state open,
- create or route an incident,
- preserve the original requested outcome for retry,
- never silently downgrade the request to "source completed".

## Reporting language

AgentOS status/reporting must distinguish:

- "code is ready"
- "CI passed"
- "deployment queued"
- "deployment failed"
- "deployed but not yet verified"
- "production verified"

This contract applies across all products and Persona Agent capabilities.


## Runtime ownership acceptance

Persistent services MUST have exactly one canonical process-manager owner.

A deployment or migration is not complete merely because the intended service unit is
`active`. Acceptance must prove that the live listener belongs to the intended owner.

For each persistent runtime, verify:

1. expected process manager and service/unit identity,
2. live listener PID for the target port/socket,
3. listener parent/cgroup ownership,
4. working directory or immutable release identity,
5. absence of a competing resurrection mechanism such as PM2/systemd/supervisor,
6. target-specific health and functional acceptance.

When migrating process managers (for example PM2 -> systemd), the old owner must be
disabled/deleted and that retirement must be persisted before the new owner is started.
Killing only the child process is insufficient because a supervisor may immediately
resurrect it.

Canonical machine-readable policy:
`governance/runtime-service-ownership.json`.
