#!/usr/bin/env bash
set -euo pipefail
SOURCE_COMMIT="${1:?source commit required}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
UNIT_DIR="$HOME/.config/systemd/user"
RELEASE_ROOT="$HOME/.local/share/agentos/monitor-runtime"
RELEASE="$RELEASE_ROOT/releases/$SOURCE_COMMIT"
mkdir -p "$UNIT_DIR" "$RELEASE_ROOT/releases" "$DATA_ROOT/runtime/monitor-runtime"
git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT" >/dev/null
rm -rf "$RELEASE"; mkdir -p "$RELEASE"
git -C "$REPO" archive "$SOURCE_COMMIT" agentos_node monitor_specs | tar -x -C "$RELEASE"
PYTHONPATH="$RELEASE" python3 -m py_compile "$RELEASE/agentos_node/monitor_runtime.py"
cat > "$UNIT_DIR/agentos-monitor-scheduler.service" <<EOF
[Unit]
Description=AgentOS Monitor Scheduler Tick
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=$RELEASE
Environment=PYTHONPATH=$RELEASE
Environment=AGENT_DATA_ROOT=$DATA_ROOT
Environment=AGENTOS_SOURCE_COMMIT=$SOURCE_COMMIT
EnvironmentFile=-$DATA_ROOT/runtime/realm/realm.env
ExecStart=/usr/bin/python3 -m agentos_node.monitor_runtime tick
TimeoutStartSec=90
CPUAccounting=true
MemoryAccounting=true
CPUQuota=50%
MemoryHigh=384M
MemoryMax=768M
EOF
cat > "$UNIT_DIR/agentos-monitor-scheduler.timer" <<'EOF'
[Unit]
Description=AgentOS Monitor Scheduler
[Timer]
OnBootSec=45s
OnUnitActiveSec=60s
AccuracySec=5s
Persistent=true
Unit=agentos-monitor-scheduler.service
[Install]
WantedBy=timers.target
EOF
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user daemon-reload
systemctl --user enable --now agentos-monitor-scheduler.timer >/dev/null
for spec in "$RELEASE"/monitor_specs/*.json; do
  PYTHONPATH="$RELEASE" AGENT_DATA_ROOT="$DATA_ROOT" python3 -m agentos_node.monitor_runtime register "$spec" >/dev/null || true
done
systemctl --user start agentos-monitor-scheduler.service || true
systemctl --user is-active --quiet agentos-monitor-scheduler.timer
echo "monitor_runtime=PASS"
