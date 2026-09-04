# Core #242 Realm restart root cause

Live Oracle bootstrap evidence on 2026-09-04 showed that the bounded runtime-converge carrier and capability marker installed successfully at exact `core/integration` source, while the durable `oracle-core-node` manifest remained on the old capability set.

The root cause was systemd activation semantics in `scripts/install_realm_fabric_user.sh`: after rewriting the user unit, the installer used `systemctl --user enable --now agentos-realm-fabric.service`. When the service was already active, that did not replace the running Python process. The old process therefore kept its old in-memory Core manifest and never projected the newly installed `node.runtime.converge` capability.

The same live bootstrap also exposed a Realm identity migration hazard: Oracle already belongs to durable Realm `realm-alston`, while `AGENTOS_REALM_ID` is unset in the host `.env`. Falling back to `realm-primary` during reinstall is incorrect. Existing durable `realm/fabric.json` identity is authoritative; an explicit conflicting environment value must fail closed.

The fix therefore requires both invariants:

1. Existing durable Realm identity is preserved unless no Realm exists yet. An explicit conflicting `AGENTOS_REALM_ID` is rejected.
2. After writing the systemd unit, the installer performs `daemon-reload`, `enable`, explicit `restart`, `is-active`, and health verification. `enable --now` alone is not accepted as a restart guarantee.

This document is source evidence only. Live `node.runtime.converge` acceptance remains dependent on a successful Oracle bootstrap and fresh ONE NodeRegistry observation.
