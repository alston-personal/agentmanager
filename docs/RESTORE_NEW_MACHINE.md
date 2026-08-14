# Restore or Provision AgentOS Node

This document defines how to provision an **AgentOS Runtime Node** on a new computer, as well as the Developer-Only source clone setup.

> [!IMPORTANT]
> **Single Source of Truth Directive**: AgentOS logic source is maintained in ONE canonical repository (Oracle Cloud VM). Client execution nodes do NOT clone full source, but install and run the versioned `agentos-runtime` package.

---

## 1. Runtime Node Installation (Recommended / Client Mode)

On any client machine, install the `agentos-runtime` package and run the node CLI:

```bash
# Install the runtime package
pip install agentos-runtime

# Inspect and verify local node status
agentos-node status

# Enroll with Central Control Plane
agentos-node enroll --gateway=https://oracle-vm.internal

# Run local diagnostic check
agentos-node doctor
```

### Harvest Ecosystem State
To collect local node handoff information and report to Central Control Plane:

```bash
python3 scripts/harvest_ecosystem.py
```

---

## 2. Developer Source Setup (Developer-Only Mode)

If you are developing or modifying the AgentOS canonical core itself on a primary workstation:

```bash
cd ~
git clone https://github.com/alston-personal/agentmanager.git
git clone https://github.com/alston-personal/my-agent-data.git agent-data
cd agentmanager
```

### Configure Local Environment
```bash
cp .env.example .env
python3 scripts/setup_env.py
```

Ensure `.env` points to your local or central data layer:
```bash
AGENT_DATA_ROOT=$HOME/agent-data
AGENT_DATA_DIR=$AGENT_DATA_ROOT
```

Set `AGENT_MODE=CORE` only on the machine that runs persistent services (such as Telegram Intake and Watchdog).

---

## 3. Data Bridges & System Health

```bash
python3 scripts/bootstrap.py
agentos-node status
python3 scripts/harvest_ecosystem.py
```

Expected result:
- `memory`, `logs`, `projects`, `knowledge` point into `agent-data`.
- `agentos-node status` reports node health as `HEALTHY`.
- `harvest_ecosystem.py` generates a master handoff snapshot in `$AGENT_DATA_ROOT/handoffs/`.
