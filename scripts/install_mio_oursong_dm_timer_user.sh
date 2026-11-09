#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" != "1001" ]; then
  echo "mio_oursong_dm_timer_install=WRONG_USER"
  exit 2
fi

SOURCE="${1:-}"
SOURCE_GUARD="${2:-}"
test -f "$SOURCE"
test -f "$SOURCE_GUARD"
GUI_PY="$HOME/.local/share/agentos/gui-worker/venv/bin/python"
test -x "$GUI_PY"
test -f "$HOME/agentmanager/scripts/mio_persona_dm_decision_user.py"
test -f "$HOME/agentmanager/scripts/mio_dm_oracle_oursong_acceptance.py"

BIN="$HOME/.local/bin"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$BIN" "$UNIT_DIR"
install -m 0755 "$SOURCE" "$BIN/mio-oursong-dm-oracle-cycle"
install -m 0644 "$SOURCE_GUARD" "$BIN/dm_loop_guard_runtime.py"

cat > "$UNIT_DIR/mio-oursong-dm-autonomous.service" <<EOF
[Unit]
Description=Mio Oursong Threads DM Autonomous Cycle
After=network-online.target agentos-gui-browser.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$HOME/agentmanager
Environment=PYTHONPATH=$HOME/agentmanager
ExecStart=$GUI_PY $BIN/mio-oursong-dm-oracle-cycle
TimeoutStartSec=210
NoNewPrivileges=true
EOF

cat > "$UNIT_DIR/mio-oursong-dm-autonomous.timer" <<'EOF'
[Unit]
Description=Wake Mio Oursong DM autonomous cycle

[Timer]
OnBootSec=4min
OnUnitActiveSec=5min
RandomizedDelaySec=30s
Persistent=true
Unit=mio-oursong-dm-autonomous.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now mio-oursong-dm-autonomous.timer >/dev/null
systemctl --user is-enabled --quiet mio-oursong-dm-autonomous.timer
systemctl --user is-active --quiet mio-oursong-dm-autonomous.timer
echo "mio_oursong_dm_timer_install=PASS"
echo "mio_oursong_dm_timer_interval=5m"
echo "mio_oursong_dm_timer_loop_guard=max_hops_2_cooldown_120s"
