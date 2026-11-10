# Governed engineering Issue intake — #470

Existing `scripts/issue_work_intake.py` previously only recognized two Lobster
read-only operations. It now separately recognizes **explicitly approved engineering
intake** by the exact labels `agentos:approved` + `agentos:engineering`
(without `agentos:readonly` / `agentos:lobster`), and single-line
`Project:`, `Action:`, `Acceptance:` fields.

Engineering Issues are registered through the **existing** typed
`agentos.work-intake/v1` entrypoint in `scripts/work_completion.py`, which
fixes the owner to `role://completion.controller`. Their workspace is intentionally
not inferred from the read-only Lobster test path. Their WorkItem is durable and
idempotent; GitHub content is task **data** only, not an executable script, an
executor authorization, a Runtime lease, or permission to deploy. Existing
Supervisor and ONE must *separately* resolve capability, grant, lease and
verification. The `execution_authorized=false` intake result is explicit.

The scheduled existing Oracle Approved Issue Intake workflow remains the only
fetch+registration carrier. The legacy automated read-only receipt-to-Issue
closure remains **read-only only** and must not close engineering Issues.
A source merge does not deploy the current Oracle Runtime or prove it consumed
`#2134`. Check live registration, WorkItem owner, acceptance, Supervisor
delivery and final receipts separately.

The absence of a controlled agent executor or permitted deployment results in
a durable blocked WorkItem, not automatic broadening of Control Inbox
`#50` or `github_actions` control-plane privileges.

For WoW #2134, the intended `Project` value is
`wow-agentos-interface`; the WorkItem ID is `gh-issue-2134-engineering`.
Use the original issue and PR #2135 as task links; do not open a second WoW
task or reproduce code within the generic intake implementation.
