# Repository Write Governance

## Canonical development rule

AgentOS runtime, Realm Fabric, Node Fabric, Desktop Executor, watchdog, reboot/network fault injection, capability-policy, and other privileged-control changes MUST NOT be written directly to `main` during active development.

Canonical working branch for the current Realm/Node/Desktop workstream:

- `feature/realm-node-fabric`

## Explicit branch invariant

Every repository mutation performed by an AgentOS/assistant automation MUST specify an explicit target branch.

Omitting the branch and allowing a tool to fall back to the repository default branch is a governance violation.

## Promotion path

1. Develop on an explicit feature branch.
2. Run unit/integration/governance acceptance checks.
3. Collect non-sensitive execution evidence.
4. Review privileged capability and rollback/recovery behavior.
5. Merge to `main` only after the workstream is accepted.

## Privileged capability rule

The following classes require feature-branch development and explicit review before promotion:

- desktop mouse/keyboard control
- window focus and screen observation
- node self-update/watchdog changes
- service/process destructive actions
- reboot/shutdown
- network disconnect/firewall fault injection
- recovery/dead-man mechanisms
- capability authorization/policy changes

Principle: stronger capability requires stronger governance.
