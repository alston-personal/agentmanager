# Issue #117 Action Relay capability group-context gate

Live exact rollout #24 proved Realm Fabric is valid and the Action Relay service starts, but the bootstrap process cannot create a capability marker temp inode in the shared spool because its effective supplementary group state does not include the already-configured `agentos` boundary.

This change does not repair or take ownership of foreign-owned spool inodes. Capability publication is delegated to a fixed publisher invoked under `/usr/bin/sg agentos -c`, matching the governed Action Relay worker boundary. The publisher verifies effective GID and parent spool GID, creates a unique same-directory temp inode, fsyncs, atomically replaces `capabilities.json`, and fsyncs the directory.

Acceptance remains fail-closed: no generic shell/argv/path authority is added to the ONE executor-job request surface, and no Experience regression PASS is claimed until a fresh exact-generation rollout reaches ONE dispatch and returns a sanitized terminal receipt.