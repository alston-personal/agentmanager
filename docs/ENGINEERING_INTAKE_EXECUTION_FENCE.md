# Engineering intake execution fence (#470, #2134)

A **durable WorkItem** is not an Executor permission grant. GitHub Issue `agentos:engineering` is accepted using the existing typed `agentos.work-intake/v1` envelope, explicitly marked `intake_kind=engineering`, `execution_authorized=false`, and remains owned by Completion Controller.

The pre-existing Work Completion Board projection can otherwise place any controller-owned accepted WorkItem in `TASK_BOARD.md`, where the Lobster loop may attempt to execute its freeform task text. This patch excludes engineering intake from that projection and adds a defense-in-depth check at Lobster's `completion_begin` boundary. Existing old engineering WorkItems are also blocked by their exact ID pattern, even before the new metadata is present. Other previously governed Lobster work remains unchanged.

This is a safety fence, not a new scheduler or a Supervisor assignment bridge. A separate authorized ONE/Employee Runtime assignment, with real identity, capability, lease and receipt, is still required; a GitHub label alone never grants shell/executor or deployment authority. A successful intake run must be reported as **ACCEPTED / NOT DISPATCHED** until that evidence is present.
