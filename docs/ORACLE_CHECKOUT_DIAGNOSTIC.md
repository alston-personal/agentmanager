# Oracle checkout diagnostic (#291)

Owner: AgentOS Core. Status: source candidate, no Oracle execution or recovery acceptance.

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

After authorization, the operator must use an exact reviewed commit ref for
`Oracle Checkout Read-only Diagnostic`. It has only `workflow_dispatch`, no caller
inputs and no push/PR trigger. It runs the reviewed script over SSH stdin using
existing deployment secrets and isolated Python; it does not import Oracle code.
The sanitized JSON artifact is retained for seven days. Credentials stay in the
SSH agent and are not part of the report.

Dispatch availability is separate from authorization: GitHub must recognize the
workflow on its default branch, and the caller must have a supported dispatch
surface. This draft does not authorize protected-main publication or assert that
the current connector can dispatch workflows. If those prerequisites are absent,
leave this candidate unexecuted and report the blocker.

Review the resulting evidence before proposing any preservation/recovery action.
Then use governed ONE convergence and its idempotency check; accept #287 only
after its separate live continuation-read checks. CI does not establish live health.
