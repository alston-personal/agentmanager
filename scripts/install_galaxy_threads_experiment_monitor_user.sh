#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "galaxy_experiment_monitor_install=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$UNIT_DIR/agentos-galaxy-experiment-monitor.service"
TIMER="$UNIT_DIR/agentos-galaxy-experiment-monitor.timer"
LOG_DIR="$HOME/agent-data/logs"
LOG="$LOG_DIR/galaxy-experiment-monitor.log"

test -f "$REPO/scripts/monitor_galaxy_threads_experiment_user.py"
test -f "$REPO/scripts/sync_sunlake_milkcat_persona_user.py"
test -f "$REPO/scripts/mio_persona_social_loop_user.py"
mkdir -p "$UNIT_DIR" "$LOG_DIR"

# Diagnose the real ubuntu-owned relay executor; do not expose binary paths,
# account state, credentials, model output, or user-private files.
PYTHONPATH="$REPO" python3 - <<'PY'
from pathlib import Path
from agentos_node.antigravity_relay_worker import discover_executor
for provider in ('claude','agy'):
    try:
        _, selected=discover_executor(provider)
        available=bool(selected and Path(selected[0]).is_file())
    except Exception:
        available=False
    print('mio_relay_'+provider+'_available='+str(available).lower())
PY
if systemctl --user is-active --quiet agentos-antigravity-relay.service; then
  echo 'mio_relay_service=ACTIVE'
else
  echo 'mio_relay_service=INACTIVE'
fi
# Relay restart is a targeted repair, not part of normal monitor reinstallation.
# Keep the background executor undisturbed during subsequent code deployments.


cat > "$SERVICE" <<EOF
[Unit]
Description=AgentOS Threads AI Subscription Experiment Monitor
After=network-online.target agentos-social-runtime.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart=/usr/bin/python3 $REPO/scripts/monitor_galaxy_threads_experiment_user.py
ExecStartPost=/bin/sh -c '/usr/bin/python3 $REPO/scripts/mio_persona_social_loop_user.py || echo mio_social_loop=DEFERRED'
ExecStartPost=/bin/sh -c '/usr/bin/python3 $REPO/scripts/sync_sunlake_milkcat_persona_user.py || echo persona_git_sync=DEFERRED'
StandardOutput=append:$LOG
StandardError=append:$LOG

[Install]
WantedBy=default.target
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Monitor Threads AI Subscription Experiment

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true
Unit=agentos-galaxy-experiment-monitor.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-galaxy-experiment-monitor.timer >/dev/null
if ! systemctl --user start agentos-galaxy-experiment-monitor.service; then
  systemctl --user --no-pager --full status agentos-galaxy-experiment-monitor.service >&2 || true
  journalctl --user -u agentos-galaxy-experiment-monitor.service -n 80 --no-pager >&2 || true
  if [ -f "$LOG" ]; then
    echo "--- galaxy monitor log tail ---" >&2
    tail -n 80 "$LOG" >&2 || true
  fi
  echo "galaxy_experiment_monitor_initial_run=FAIL" >&2
  exit 4
fi
systemctl --user is-enabled --quiet agentos-galaxy-experiment-monitor.timer
systemctl --user is-active --quiet agentos-galaxy-experiment-monitor.timer

SNAPSHOT="$HOME/agent-data/runtime/social/experiments/ai-subscription/latest.json"
test -f "$SNAPSHOT"
python3 - "$SNAPSHOT" <<'PY'
import json, sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
assert p.get('schema')=='agentos.social-experiment-snapshot/v1',p
assert p.get('experiment')=='ai-pays-its-subscription',p
print('galaxy_experiment_monitor_snapshot=PASS')
print('galaxy_experiment_monitor_reply_count='+str(p.get('reply_count',0)))
print('galaxy_experiment_monitor_new_replies='+str(len(p.get('new_replies') or [])))
print('galaxy_experiment_monitor_needs_attention='+str(bool(p.get('needs_attention'))).lower())
PY

HISTORY="$HOME/agent-data/runtime/social/experiments/ai-subscription/history.jsonl"
if [ -f "$HISTORY" ]; then
python3 - "$HISTORY" <<'PY'
import json, sys
seen={}
for raw in open(sys.argv[1],encoding='utf-8'):
    try: row=json.loads(raw)
    except Exception: continue
    for item in row.get('new_replies') or []:
        rid=str(item.get('id') or '')
        if rid:
            seen[rid]={
              'id':rid,
              'username':item.get('username'),
              'text':item.get('text'),
              'timestamp':item.get('timestamp'),
              'permalink':item.get('permalink'),
            }
print('galaxy_experiment_monitor_reply_catalog='+json.dumps(list(seen.values()),ensure_ascii=False,separators=(',',':')))
PY
fi

echo "galaxy_experiment_monitor_install=PASS"
echo "galaxy_experiment_monitor_interval=10m"
echo "galaxy_experiment_monitor_log=$LOG"
if [ -f "$LOG" ]; then
  tail -n 160 "$LOG" | grep -E '^(mio_social_loop=|mio_social_decision=|mio_social_publish=|mio_social_pending=|mio_social_new_external=|mio_social_outbound=|mio_social_outbound_today=|mio_life_event=|mio_energy=)' | tail -n 50 || true
fi
