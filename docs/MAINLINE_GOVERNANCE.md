# AgentOS Mainline Governance

Status: canonical governance contract once merged.

## Invariant

Development execution authority is not mainline publication authority.

No executor, agent, workflow, automation, IDE surface, connector, or `/goal` continuation may write development mutations directly to the canonical `main` branch merely because it has repository write capability.

Normal path:

`goal/task -> non-main branch -> tests/evidence -> pull request -> governed promotion -> main`

Statements such as `continue`, `finish it`, `keep going until done`, or autonomous-goal execution do not grant mainline publication authority.

## Mainline publication authority

A mutation may enter `main` only through a GitHub pull request protected by the repository mainline ruleset. The protected branch must reject direct pushes, including administrator bypass unless a separately governed break-glass procedure is explicitly invoked.

Production deployment authority remains separate from repository publication authority. A live deployment receipt, lease, generation advance, or acceptance result never grants permission to push source/evidence directly to `main`.

## Break glass

Emergency publication is deny-by-default. A future break-glass mechanism must require an explicit user authorization event, a unique incident identifier, bounded scope, immutable receipt, and post-incident review. Until that mechanism exists, there is no emergency direct-push exception.

## Executor rule

Before any repository mutation, an executor must resolve the target branch explicitly. If the resolved target is `main`/the default branch and the operation is not an already-authorized governed promotion, the executor must refuse that mutation and create/use a task branch instead.

Repository APIs whose branch argument is optional must never be called without an explicit non-main branch for development work.

## Platform enforcement required

The repository must have a GitHub branch protection/ruleset for `main` requiring pull requests and the `Mainline Governance Guard` status check, while blocking direct pushes. Documentation and CI are defense-in-depth; GitHub branch protection is the final publication fence.
