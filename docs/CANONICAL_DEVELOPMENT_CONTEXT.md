# Canonical Development Context

This document is the human-readable companion to `.agentos/development-context.json`.

## Canonical branch model

- `main` = stable / production baseline.
- `feature/distributed-agentos-runtime` = the single AgentOS vNext integration branch and the canonical continuation point for current research and implementation.
- New feature branches are exceptional and short-lived. They must declare a parent, merge target, purpose, and completion condition.

## Mandatory write rule

Every GitHub write must name its branch explicitly. Omitting `branch` and allowing the tool/API to fall back to the repository default is forbidden for experimental work. Experimental writes to `main` fail closed unless production promotion is explicitly intended and authorized.

This rule exists because a real incident on 2026-08-24 showed that semantic knowledge of the intended branch was not enough: a local task to create an Oracle runner probe omitted the branch argument, causing GitHub to write to `main`. AgentOS therefore treats branch, repo, write policy, and merge target as execution constraints that must propagate into every tool call.

## Current branch inventory

### Keep

**`main`** — stable/production baseline. Six Oracle probe/evidence commits from the 2026-08-24 incident landed here accidentally. Do not stack further experimental work on them; reconcile them deliberately later.

**`feature/distributed-agentos-runtime`** — ACTIVE canonical development branch. Draft PR #2 targets `main`. This branch already contains the Distributed AgentOS runtime, Canonical IR, Control Plane continuity, runtime dispatch/provider bridge work, State Kernel integration, Master Experience Floor research, and related tests. Continue Node Join / Cognitive Bridge work here.

### Retire

**`feature/state-kernel-v2`** — PR #3 was merged into `feature/distributed-agentos-runtime`. It has no commits ahead of the integration branch.

**`feature/watchdog-backoff`** — has no commits ahead of the integration branch and is hundreds of commits behind. It is historical only.

**`feature/node-cognitive-bridge-v0`** — created from the wrong lineage during the 2026-08-24 incident. It contains only the accidental Oracle probe/evidence delta and is far behind the integration branch. Do not develop on it.

### Audit before retire

**`agent/auto-pushing`** — diverged legacy branch with four unique commits. It contains agent rules, a Redmine porting skill, and watchdog/lobster/systemd/LiteLLM changes. Review and selectively salvage useful changes; do not merge the branch wholesale because it is far behind the integration branch.

## Current active work

Goal: complete AgentOS Node Join / Cognitive Bridge and test whether AgentOS can preserve Master Experience Floor continuity on a real Oracle Antigravity executor.

Verified findings:

1. Oracle host `instance-20260129-0852` is an online GitHub self-hosted runner using service account `agentos-node`.
2. GitHub -> Oracle execution has been proven by committed evidence.
3. `agentos-node` can read `/home/ubuntu/agentmanager` and `/home/ubuntu/agent-data` but cannot write them; Git also rejects those cross-owner repos as dubious ownership.
4. The Oracle Antigravity executor could reconstruct substantial local context but explicitly reported the ONE canonical state as unavailable.
5. Therefore machine transport is working, but cognitive continuity/state binding is incomplete.

Next sequence:

1. Define a controlled workspace access contract for `agentos-node`; do not grant blanket sudo or transfer ownership of the existing Ubuntu workspaces.
2. Implement the minimum Node Cognitive Bridge on the integration branch: canonical state resolve -> execution capsule -> executor -> receipt -> reconcile.
3. Repeat the original fresh-session Antigravity `/goal` continuation test without manually revealing the active goal.
4. Preserve before/after evidence and update research claims only after the receipt/reconciliation chain is verified.

## Fresh-agent bootstrap

A fresh executor working on this repository must:

1. Read `AGENTS.md`.
2. Read `.agentos/development-context.json` and this document.
3. Confirm the current checked-out branch before any write.
4. Treat `feature/distributed-agentos-runtime` as the default continuation branch for current AgentOS vNext work.
5. If shared Canonical IR/Control Plane state is reachable, prefer it over this document for live goal/task state. This file is the development-governance fallback, not a replacement for runtime canonical state.
6. Never infer a new branch merely because the task sounds like a new feature.

## Principle exposed by the incident

Goal continuity alone is insufficient. AgentOS must canonicalize and propagate execution constraints as well: repository, branch, authority, protected refs, evidence destination, and merge target. A capable executor that understands the goal can still violate governance if those constraints disappear at the final tool boundary.
