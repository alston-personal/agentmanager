# Oracle checkout diagnostic (#291)

Owner: AgentOS Core. Status: bounded read-only live evidence obtained; recovery acceptance remains open.

The governed convergence request for `b65dc309d6a020b27f591d938a0589206003a0ea`
failed with `tracked_checkout_dirty`:
https://github.com/alston-personal/agentmanager/issues/50#issuecomment-5595376433
That receipt does not identify the dirty paths or prove which relay generation ran.

## Fixed scope

`scripts/oracle_checkout_diagnostic.py` uses only the Python standard library and
fixed read-only Git operations against `/home/ubuntu/agentmanager`. It checks the
canonical origin, reports HEAD and at most 128 tracked relative paths, statuses,
and SHA-256 digests for regular files up to 2 MiB. Symlinks, including directory
components, are not followed. Untracked files and file bodies are not exported.
Target blob equality is reported only if the fixed target object already exists
locally; no network fetch or object materialization is requested.

Matching content is evidence only: index state, modes and provenance still matter.
All changes remain classified as unknown user/runtime changes and automatic
recovery remains false. Rechecking HEAD/status detects some concurrent changes;
it is not an atomic filesystem snapshot. A failure emits a generic diagnostic
error without subprocess stderr or exception contents.

There is no checkout, reset, stash, deletion, installer, service restart, or runtime
mutation. The script rejects caller arguments. Read access may update filesystem
access times; `mutation_performed` describes intentional repository/runtime writes.

## Explicit bootstrap execution boundary

Issue #291 requires explicit authorization for this one-time GitHub Actions
bootstrap/evidence path. Preparing, testing or merging this source does not grant
execution permission. ONE failures must not trigger the workflow automatically.

The 2026-09-09 canonical Core conversation explicitly authorized this diagnostic.
An isolated execution branch activated a push trigger; it is not an integration
candidate or a steady-state control channel. The hosted SSH attempt stopped
before connection because host configuration was absent. Direct runner execution
then correctly hit Git ownership protection. The successful attempt used the
existing Oracle runner labels and existing deployment identity over localhost SSH,
without disabling Git ownership checks, checking out source, or invoking recovery.

The canonical manual workflow embeds the exact tested standalone script; a test
prevents divergence. It uses no caller inputs and no push/PR trigger. It returns
bounded JSON in workflow logs, not repository file bodies. Existing SSH credentials
stay inside the agent. Temporary runner/SSH agent bookkeeping is not runtime
checkout mutation. No protected-main publication is authorized.

## Observed evidence

Successful run: https://github.com/alston-personal/agentmanager/actions/runs/34320081009

At `2026-09-09T06:39:50Z`, the checkout HEAD was
`28be69cb671fcf8cedd5abc8864dda88c4b03dd6`; tracked dirty paths were empty and
HEAD/status were stable during the read. The sanitized receipt is stored in
`.agentos/evidence/runtime-converge/checkout-diagnostic-20260909.json`.

The earlier dirty condition had already changed before this successful read.
This evidence does not establish the cause, ownership or disposition of the earlier
changes. No recovery was performed by this diagnostic. A clean checkout alone does
not establish runtime health, installer correctness or #287 continuation acceptance.

Review the resulting evidence before proposing any preservation/recovery action.
Then use governed ONE convergence and its idempotency check; accept #287 only
after its separate live continuation-read checks. CI does not establish live health.

## Governed follow-up

At `2026-09-09T08:42:46Z`, a fresh ONE `node.runtime.converge` request for the
same `28be69cb` generation returned `CURRENT_GENERATION_RECONCILE_FAILED`,
`ok=false`, `health=failed`, `idempotent=true`, `rollback=not_needed`.
Receipt: https://github.com/alston-personal/agentmanager/issues/50#issuecomment-5598994002

The sanitized result is stored in
`.agentos/evidence/runtime-converge/clean-checkout-reconcile-20260909.json`.
This is not a successful idempotence or health acceptance. A second identical
attempt is not useful until the reconciliation failure is resolved.

PR #298 documents a separate malformed Realm Fabric state blocker and supplies
atomic updates plus explicit hash-bound tail repair. It explicitly does not repair
the live file merely by merging source. That is a relevant unresolved dependency,
not proof that it caused this exact failure: the convergence receipt currently
collapses installer/service/health failures into one classification. Recovery of
Realm data is outside this checkout-only diagnostic authorization and was not run.
#291 and #287 live acceptance remain open.
