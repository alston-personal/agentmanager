# Core Supervisor installation contract

Status: **source deployment contract only; Oracle live activation and operating acceptance remain pending**.

The Core Supervisor is the single persistent Core reconciliation process. Employees are durable identities, not per-role daemons.

## Actual Linux install path

The existing Core deploy carrier eventually calls:

```text
scripts/install_services.py
  -> LinuxPlatformDriver.install_background_services()
  -> scripts/install_systemd_user.sh
  -> systemctl --user
```

Therefore `agentos-core-supervisor.service` is a **user service**. The source asset must not contain a fixed `User=` directive and uses `WantedBy=default.target`. During installation, host-specific checkout, Python, configuration, and data-root paths are rendered into the user unit.

Repository merge does not run this installer. Running the deploy carrier, installing/restarting the service, or changing the host-local delivery gate is a privileged runtime mutation requiring separate authority and evidence.

## Safe default: S3 observe/plan

On a CORE host, the installer materializes and enables the persistent Supervisor. If the host-local Supervisor environment does not yet exist, it is created with:

```text
AGENTOS_SUPERVISOR_DELIVERY_MODE=disabled
```

An existing host-local `core-supervisor.env` is preserved rather than overwritten from the repository example. The base unit retains `PrivateNetwork=true`, `NoNewPrivileges=true`, `ProtectSystem=strict`, and only the Employee runtime is writable.

This means a normal Core service installation can make the reconciliation heart persistent without silently granting the S4 ONE delivery boundary.

## Explicit S4 one_direct gate

Installer wiring for S4 requires:

```text
AGENTOS_CORE_SUPERVISOR_ENABLE_ONE_DIRECT=1
```

and both pre-existing canonical ONE files:

```text
$AGENT_DATA_ROOT/realm/fabric.json
$AGENT_DATA_ROOT/realm/nodes.json
```

If either file is absent, installation fails closed. The installer does **not** initialize a Realm or create shadow ONE state.

With the explicit gate, the installer renders the narrow filesystem drop-in and a host-local delivery environment containing:

```text
AGENTOS_SUPERVISOR_DELIVERY_MODE=one_direct
AGENTOS_SUPERVISOR_ONE_DATA_ROOT=$AGENT_DATA_ROOT
```

The drop-in grants write access only to the existing `realm/` store needed by the local file-backed ONE queue. `PrivateNetwork=true` remains in force. There is no GitHub Actions fallback.

If the base host environment itself requests `one_direct` but the explicit install gate is absent, installation refuses to proceed. This prevents a routine deploy from silently inheriting expanded delivery authority.

## What this still does not prove

Even after this source contract merges, neither marker is valid until a governed live run occurs:

- `CORE_SUPERVISOR_PERSISTENT_RECONCILIATION=VERIFIED`
- `SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED`

The live acceptance must still prove the real Supervisor process, existing ONE/Node boundary, Node receipt, Employee generation-1 checkpoint, executor/process turnover, generation-2+ resume, memory/thread continuity, sanitized terminal receipt, and terminal wake suppression without a user saying `繼續`.

**Repository merge != installer execution != Oracle deployment != operating acceptance.**
