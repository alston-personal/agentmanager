# Atlas #22 approved WorkItem -> existing Paw read-only Assignment

The original Atlas authority remains `alston-personal/my-agent-data#22`, and its foundational PR #21 is merged into `my-agent-data/main` (merge `b456f797766c868298c8961642cb4074117f4387`). AgentOS `#2243` is only an existing-repository engineering-intake carrier because the current scheduled intake is scoped to `agentmanager`.

## Source of truth and exact matching

The installed Core intake can register `gh-issue-2243-engineering` in the existing Completion Ledger, owned by `role://completion.controller`, with `intake_kind=engineering`, `project_id=agentos-atlas`, canonical source `https://github.com/alston-personal/agentmanager/issues/2243` and `execution_authorized=false`. The source-only gate `scripts/approved_atlas_paw_handoff.py` fails closed unless these fields exactly match and the work is accepted/in_progress with a nonempty acceptance contract.

The existing Oracle Approved Issue Intake runs this gate from the installed immutable Core Runtime. It projects only a **read-only** work item + pending Employee assignment `paw-atlas-2243-inspect-v1` to the already-registered employee `the-paw` with role `sector.paw` and skill `engineering.work.inspect`. It uses the existing `WorkItemStore` and `EmployeeRuntime`; reruns are idempotent, and conflicting assignments fail closed. If the accepted WorkItem is absent, waiting or terminal, it emits a non-registration receipt without creating work, resetting retries, or claiming a lease.

## Evidence and authority boundaries

The existing Oracle intake logs bounded `atlas_2243_* ` readbacks of the exact Completion WorkItem, admission owner, `execution_authorized`, assignment registration/state and lease state; it does not log credentials, raw Issue prose, private memories, or untrusted task text. An intake workflow `SUCCESS` is **not** a claim that Atlas was installed or Employee delivery succeeded.

The projection grants **no** shell, model, repository write/merge, production deployment, Node/Realm selection, S4 enablement, lease, assignment claim, or Completion WorkItem closure. `engineering.work.inspect` remains limited to observation and reporting blockers. Any production action or engineering implementation still requires its own independently authorized ONE/Employee capability and a verifiable receipt. The Core Supervisor controls S4 delivery; Atlas does not create a competing queue or scheduler.

## Minimum autonomy acceptance remains open

1. PR for this exact-scope projection passes existing CI and merges under governance.
2. Immutable Oracle Runtime rolls out the precise merged source. Read the installed version.
3. Oracle intake reports exact `gh-issue-2243-engineering` and `paw-atlas-2243-inspect-v1` as registered; separately observe real S4 delivery, employee lease/claim, terminal Lifecycle receipt.
4. Actual Atlas Delta ingress writes a durable evidence Receipt; fresh session/device reads that same canonical project Resume Packet, then existing Supervisor continues an independently authorized next task.
5. External Controller/Watchdog detects Atlas itself when stale or blocked.

Until step 4 and the autonomous follow-up Receipt pass, original Atlas #22 stays OPEN. No passive ChatGPT transcript harvesting claim: the explicit authorized delta adapter is the only supported source path.
