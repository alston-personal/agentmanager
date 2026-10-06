#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_threads_session_supervisor_install=WRONG_USER" >&2
  exit 2
fi

SOURCE_COMMIT="${1:-${AGENTOS_SOURCE_COMMIT:-}}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
ROOT="$HOME/.local/share/agentos/mio-threads-session-supervisor"
RELEASE="$ROOT/releases/$SOURCE_COMMIT"
UNIT_DIR="$HOME/.config/systemd/user"

rm -rf "$RELEASE"
mkdir -p "$RELEASE/scripts" "$UNIT_DIR"
git -C "$REPO" show "$SOURCE_COMMIT:scripts/probe_threads_web_dm_login_user.sh" > "$RELEASE/scripts/probe_threads_web_dm_login_user.sh"
git -C "$REPO" show "$SOURCE_COMMIT:scripts/run_mio_threads_session_supervisor_user.sh" > "$RELEASE/scripts/run_mio_threads_session_supervisor_user.sh"
chmod 700 "$RELEASE/scripts/"*.sh

cat > "$UNIT_DIR/mio-threads-session-supervisor.service" <<EOF
[Unit]
Description=Mio Threads Session Supervisor
After=network-online.target agentos-gui-browser.service
Wants=network-online.target

[Service]
Type=oneshot
Environment=AGENT_DATA_ROOT=/home/ubuntu/agent-data
ExecStart=/bin/bash $RELEASE/scripts/run_mio_threads_session_supervisor_user.sh
EOF

cat > "$UNIT_DIR/mio-threads-session-supervisor.timer" <<'EOF'
[Unit]
Description=Run Mio Threads Session Supervisor

[Timer]
OnBootSec=15min
OnUnitActiveSec=2h
RandomizedDelaySec=10min
Persistent=true
Unit=mio-threads-session-supervisor.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now mio-threads-session-supervisor.timer >/dev/null
systemctl --user start mio-threads-session-supervisor.service
systemctl --user is-active --quiet mio-threads-session-supervisor.timer
echo "mio_threads_session_supervisor_install=PASS"
echo "mio_threads_session_supervisor_interval=2h"
echo "mio_threads_session_supervisor_persistent=true"
