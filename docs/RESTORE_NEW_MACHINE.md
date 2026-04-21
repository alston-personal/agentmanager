# Restore AgentOS on a New Machine

This is the cold-start checklist for making AgentOS whole after cloning to another computer.

## 1. Clone the Logic and Data Layers

```bash
cd ~
git clone https://github.com/alston-personal/agentmanager.git
git clone https://github.com/alston-personal/my-agent-data.git agent-data
cd agentmanager
```

## 2. Configure the Local Environment

```bash
cp .env.example .env
python3 scripts/setup_env.py
```

At minimum, `.env` must point at the data repo:

```bash
AGENT_DATA_ROOT=$HOME/agent-data
AGENT_DATA_DIR=$AGENT_DATA_ROOT
```

Set `AGENT_MODE=CORE` only on the machine that should run always-on services such as Telegram command intake and the watchdog.

## 3. Rebuild the Data Bridges

```bash
python3 scripts/bootstrap.py
/bin/bash scripts/health_check.sh
python3 scripts/run_workflow.py status
```

Expected result:

- `memory`, `logs`, `projects`, `projects_status`, `knowledge`, and `ARCHITECTURE.md` point into `agent-data`.
- `python3 scripts/run_workflow.py status` lists projects from `agent_core.project_store`.
- Projects should show `fresh` unless the data layer is intentionally old.

## 4. Install Services on a Core Machine

```bash
bash scripts/install_systemd_user.sh
systemctl --user status os-pulse.service
systemctl --user status agent-maintenance.timer
systemctl --user status tg-commander.service
systemctl --user status cat-ink-syncer.service
```

The installer writes portable units into `~/.config/systemd/user` using the current clone path and `AGENT_DATA_ROOT`. It starts `tg-commander.service` and `cat-ink-syncer.service` only when `AGENT_MODE=CORE`.

## 5. Sync and Resume

```bash
/bin/bash scripts/sync_brain.sh
python3 scripts/internalize.py
python3 scripts/recall_chronicle.py
```

The active memory handoff is in:

```text
$AGENT_DATA_ROOT/memory/session_sync.md
```

The operational knowledge page is:

```text
$AGENT_DATA_ROOT/knowledge/system/AgentOS_Operational_State.md
```

## Recovery Commit

The April 21, 2026 recovery checkpoint is split across both repositories:

- Logic: `Restore AgentOS core recovery pipeline`, then `Improve project yaml initialization`
- Data: `Sync AgentOS recovery memory state`, then `Add project yaml coverage for legacy projects`

Pull both repos before diagnosing an old machine.
