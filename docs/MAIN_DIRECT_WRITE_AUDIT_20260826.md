# Main Direct-Write Audit — 2026-08-26

## Summary

A sequence of AgentOS Realm/Node/Desktop commits was written directly to `main` because repository mutation calls omitted an explicit branch and therefore fell back to the default branch.

This was a workflow-governance violation. It does not mean all affected commits should now be reverted: several are already part of the currently working Windows Node/Realm acceptance path.

## Canonical continuation branch

All further work in this workstream continues on:

- `feature/realm-node-fabric`

## Classification

### A. Runtime/core changes currently worth preserving

These changes are already part of the validated Realm/Windows-node path and should not be blindly reverted from main:

- Windows Thin Client install/pinning fixes
- node enrollment/approval support used by the first external Windows node
- Realm node probe/control acceptance plumbing
- `agentos_node/interactive_desktop.py`
- Thin Client desktop capability exposure
- ShellExecuteW URL-launch fix
- desktop session inspection
- desktop visible-window inspection

Representative commits include:

- `8a02e47a529967f76cc62e8d1a5b2c2f5420f4f5` — add Windows interactive desktop adapter
- `8df5de3b9b53e45c8fffec1605920a1510ad6855` — expose governed interactive desktop capabilities
- `89ee441f41d182973f1d01f20d889376dc4db883` — install interactive desktop adapter
- `1433579c70a68e854a938e934623d65dbea00980` — launch URLs through ShellExecuteW
- `70de83e0c91e8dd981b3069886b1fb071971e526` — inspect interactive desktop windows
- `424734a2b5395eb87b697dcce4d2298206fb44fa` — expose desktop window inspection

### B. Acceptance-test / command-trigger material

These are useful as experiment history but should be reviewed for relocation, consolidation, or removal from long-lived main once the feature branch has a stable acceptance suite:

- one-off `.agentos/commands/*` trigger mutations
- one-off workflow files created only to exercise a single acceptance path
- direct-browser-control probes
- repeated self-update trigger commits
- repeated desktop/session probe commits

### C. Evidence churn

Repeated evidence commits are useful for research provenance, but should not become the primary mechanism for sensitive or high-frequency runtime evidence.

Policy direction:

- keep non-sensitive acceptance summaries in Git
- keep screen captures/private desktop evidence out of the public repository
- move high-frequency receipts to the Realm evidence store / ledger
- retain only durable acceptance milestones in Git

### D. Self-update path requiring redesign

The current self-update bootstrap exposed a lifecycle race: the daemon can be asked to update/restart itself while it is still responsible for returning the receipt.

Do not promote additional self-update work until the branch contains an independent updater/watchdog model.

## Main cleanup policy

Do NOT bulk-revert the AgentOS commits from main.

Reason:

1. today’s validated Windows Node path depends on some of them;
2. unrelated work (including other projects) is interleaved on main;
3. a broad revert risks removing working production/research capability.

Instead:

1. freeze further privileged AgentOS direct writes to main;
2. continue development on `feature/realm-node-fabric`;
3. consolidate one-off workflows/triggers into stable acceptance tooling on the branch;
4. identify files that are experiment-only and selectively remove them from main in a dedicated cleanup PR;
5. merge the stabilized branch only after governance and recovery acceptance.

## Repository invariant

All repository mutations must name an explicit branch. Default-branch fallback is forbidden for governed AgentOS development.

Principle: stronger capability requires stronger governance.
