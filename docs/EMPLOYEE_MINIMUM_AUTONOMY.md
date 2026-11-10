# Minimum autonomous operation gate for all new Employees

A new god/Employee **may start with only one bounded capability**, but must **not** be described as an operating role until evidence proves it independently continues working.

## Source declaration is not activation
1. Inherit `core.root`, register stable role ID and durable Employee identity.
2. Register one **real callable** read-only or otherwise explicitly governed skill, with its permission grant; don't rely on a natural-language prompt as the executor.
3. Provide an idempotent Employee bootstrap, stable WorkItem, persistent checkpoint, and a specific output artifact.
4. Reuse existing ONE, Supervisor, Scheduler and Completion Ledger, with no per-role daemon or parallel queue.
5. Show one scheduled wake, claim, executable skill invocation, checkpoint, sanitized output receipt.
6. Show the **next** scheduled wake/claim/receipt without a human saying "繼續", and preserve continuity across restart/executor replacement.
7. Check results through `agent_core.employee_autonomy_gate`; only independently validated evidence can yield `LIVE_VERIFIED`.
8. After minimum operation is verified, iterate optional skills, richer intelligence and UI. Do not block minimum liveness on feature completeness.

## Hermes #2120
Initial contract is public GitHub metadata research and dedup, with advisory dynamic cadence (1–168 hours) bounded by existing Scheduler grants, budget and host health. Current source files are not proof of installation, wake or recurring operation. No new role may self-assign arbitrary work; the scheduler must perform controlled next-cycle creation.

The activation path is: deploy approved source → hydrate `research.hermes` → explicitly bootstrap `hermes-technology-scout` → register an allowlisted scanning skill and existing scheduler wake → observe real ONE receipts for two independent cycles → check gate. If any step is absent, status is `NOT_VERIFIED`.

Avoid creating a GitHub Actions cron as substitute. Protect current #470 and #1682 priorities.
