# AgentOS Platform Drivers

AgentOS now treats the operating system as an implementation detail.

## Layers

- `agent_core/platform/base.py`
  - Shared filesystem and process helpers
  - Pulse/event writes
  - Locking
  - Transcript sync
  - Project link repair
- `agent_core/platform/linux.py`
  - Linux-specific service integration
  - `systemd --user`
  - `/dev/shm/leopardcat-swarm`
- `agent_core/platform/windows.py`
  - Local runtime directory fallback
  - Subprocess-backed service registry
  - No `systemd` dependency
- `agent_core/platform/macos.py`
  - macOS runtime paths
  - Same service fallback model as Windows

## Entry Points

- `scripts/pulse.py`
  - Writes heartbeat state through the selected driver
- `scripts/install_services.py`
  - Installs background services for the current platform
- `scripts/platform_runtime.py`
  - Diagnostics and runtime/service management helper

## Session Close

The session lifecycle is handled by `agent_core/session_lifecycle.py` and is used by:

- `scripts/run_workflow.py` for `/report`
- `scripts/handover.py` as a compatibility wrapper

Session close now writes:

- structured session YAML records
- compact `SHORT_TERM.md` updates
- compact `STATUS.md` updates
- compact `session_sync.md` handoff entries

Raw Telegram transcripts stay in the Telegram transcript store and no longer share the same logical buffer as the handoff stream.

For project-local memory writes, `agent_core/memory_router.py` resolves the destination first, so `SHORT_TERM.md`, `LONG_TERM.md`, and transcripts follow the active project context instead of whichever workspace opened first.
