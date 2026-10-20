---
name: anti-slop-delivery
description: Prevent work that substitutes PRs, plans, explanations or CI for a user-visible outcome. Apply to coding, operations, deployments, autonomous agent handoffs and completion claims.
---
# Anti-slop delivery gate (original AgentOS adaptation)

Use this *before* declaring success and before generating another issue, branch or report.

1. Write a concrete user-visible acceptance condition and probe, e.g. production API contains a named persona and a real single-card reading succeeds.
2. Discover existing owners, executable capabilities, current runbooks and historical proven solutions *before* inventing infrastructure.
3. Minimize change: one owner lane, one fix, targeted tests. Avoid redundant issues and decorative refactors.
4. Separate states: CODED, TESTED, MERGED, DEPLOYED, PRODUCTION_VERIFIED. Never infer the next state from the previous.
5. Capture source SHA, execution identity, environment, artifact, rollback, runtime health and public acceptance evidence.
6. Mocked tests establish plumbing only, never real LLM quality or production success.
7. If action/permission is unavailable, identify exact blocker and supported executor; do not run obsolete fixed-SHA deployment paths.
8. Use persisted scheduler/executor for continuation if supported. A chat response or Issue comment is not autonomous work.
9. Claim DONE only after evidence supports the user's requested outcome. Otherwise label BLOCKED with an actionable next step.

FAIL patterns: multiple '繼續' turns with only reports; green PR described as production; fake successful receipt; repeated rediscovery; opening parallel tasks; writing runbooks instead of fixing an executable defect; unverified runtime changes.

Output: concise evidence receipt: goal, repo, source SHA, runtime environment, acceptance probe, observed result, status and timestamp. Empty/unknown fields must be explicitly unknown.

This is an original skill informed by delivery quality ideas in https://github.com/zansxart/anti-slop ; not copied from upstream.
