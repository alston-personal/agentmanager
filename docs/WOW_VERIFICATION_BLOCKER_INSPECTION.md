## Verification retry budget and independent read-only diagnosis

Oracle [#42542432721](https://github.com/alston-personal/agentmanager/actions/runs/42542432721) confirms WoW WorkItem `gh-issue-2134-engineering` is `blocked` with `last_blocker_kind=VERIFICATION` after the existing Completion Ledger exhausted its finite retry admission. The original item MUST NOT be reset, continued, or marked DONE just to obtain progress.

This narrowly permits one independently scoped `paw-wow-2134-inspect-v1` **read-only** Employee Assignment *only* when that exact canonical WoW WorkItem is blocked due to VERIFICATION and its machine retry count is >=5. Other blockers, including human authorization, remain unassigned. Source authorization, exact project/Issue identity, role and skill checks are unchanged. The original WorkItem stays blocked, and no executor provider, shell, model, deployment, merge, receipt or lease is assigned by this projection. Actual ONE/Supervisor delivery still requires a separate governed claim.

This is an investigation of the failed verification **not a retry** of the original WoW engineering task. Paw must produce grounded evidence identifying the blocker or escalate for independently authorized repair, not report MVP completion.
