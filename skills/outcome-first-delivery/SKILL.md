# Outcome-first delivery guard (AgentOS Skill)

## Mission
Prevent agent work from degenerating into explanation, PR proliferation, and repeated
human "continue" prompts. The user's requested observable outcome is the contract.

## Mandatory task record
Before execution, persist:
- `goal_id`, `user_outcome`, `acceptance_probe`, `evidence_location`
- `owner`, `next_action`, `resume_trigger`, `blocker_type`
- `baseline`, `attempt_count`, `last_verified_result`
A PR, commit, plan, green unit test, or workflow dispatch is never the user outcome.

## Execution loop (enforced by runtime, not by prompting alone)
1. Read the persisted goal and latest receipt; never restart discovery without checking it.
2. Choose the shortest authorized action toward the acceptance probe.
3. Execute it. Store immutable receipts and update the goal atomically.
4. Run the acceptance probe against the requested environment.
5. If FAIL: classify exact failure; retry only with a changed hypothesis and bounded budget.
6. If PASS: record verified completion, then claim the next queued task without a human "continue".
7. If HUMAN_REQUIRED: ask only for the precise permission, secret, or interactive action needed.
8. If a tool/runner is unavailable: persist BLOCKED with retry trigger and route to the existing
   scheduler/executor. Do not pretend this chat will keep running in the background.

## Hard gates
- **Outcome gate:** completion requires evidence from the user-facing acceptance probe.
- **Branch gate:** one active implementation lane per goal. No new PR/Issue unless existing
  lane is unsuitable and the old lane is explicitly superseded with a linked receipt.
- **Detour gate:** ancillary governance/test work requires a demonstrated direct dependency
  on the user outcome and a bounded scope. Otherwise return to the primary path.
- **Repeat gate:** no second unchanged diagnosis or unchanged tool call. Record the
  previous result and alter the approach or escalate the specific blocker.
- **Progress gate:** report three separate fields: implemented, deployed, verified.
  Never substitute one for another.
- **Human-interruption gate:** no repeated "continue" request. Only interrupt for an
  action that cannot be performed by authorized tools.
- **Safety gate:** do not bypass branch protection, deployment authority, secrets,
  approval, or rollback policy to achieve a faster result.

## Example: ocean-current-master
User outcome: production site selects Ocean Current Master and returns one real card reading.
Acceptance: live persona API contains the persona AND a real single-card reading succeeds
with its actual provider/engine result. Frontend-only mock and local-only tests are insufficient.
Current partial deliverables (#86, Core #2079) are dependencies, NOT completion.
The owner must focus on a governed backend deploy/rollback carrier, then collect live receipts.
If Oracle executor is queued, record the exact run and resumption trigger; do not add unrelated PRs.

## Reporting format
`Goal: ... | Implemented: ... | Deployed: ... | Verified: ... | Blocker: ... | Next automatic action: ...`
Only claim "automatic" when a durable scheduler/trigger actually exists and is enabled.

## Growth proof
For a fixed benchmark suite, track outcome success rate, human prompts per completed
goal, time-to-recovery, repeated-failure rate, and unrelated PRs per goal. Compare
against baseline; a prettier report or more PRs is not learning.
