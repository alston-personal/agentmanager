#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: bootstrap scheduler rollout must run as ubuntu" >&2
  exit 2
fi

SOURCE_COMMIT="${1:-}"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
UNIT_DIR="$HOME/.config/systemd/user"
STATE_ROOT="$DATA_ROOT/runtime/bootstrap-scheduler"
MARKER="$STATE_ROOT/enabled"
LOCK_ROOT=/tmp/agentos-locks

mkdir -p "$UNIT_DIR" "$STATE_ROOT" "$LOCK_ROOT"
exec 9>"$LOCK_ROOT/oracle-core-runtime.lock"
flock -w 120 9

git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT" >/dev/null
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
for rel in agentos_node/bootstrap_control.py agentos_node/bootstrap_scheduler.py; do
  mkdir -p "$TMP/$(dirname "$rel")"
  git -C "$REPO" show "$SOURCE_COMMIT:$rel" > "$TMP/$rel"
done
python3 -m py_compile "$TMP/agentos_node/bootstrap_control.py" "$TMP/agentos_node/bootstrap_scheduler.py"

install -m 0664 "$TMP/agentos_node/bootstrap_control.py" "$REPO/agentos_node/bootstrap_control.py"
install -m 0664 "$TMP/agentos_node/bootstrap_scheduler.py" "$REPO/agentos_node/bootstrap_scheduler.py"
python3 -m py_compile "$REPO/agentos_node/bootstrap_control.py" "$REPO/agentos_node/bootstrap_scheduler.py"

write_unit() {
  local unit="$1" role="$2" worker="$3" cpu="$4" mem_high="$5" mem_max="$6"
  cat > "$UNIT_DIR/$unit" <<EOF
[Unit]
Description=AgentOS Bootstrap Scheduler Worker $worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
Environment=AGENTOS_BOOTSTRAP_ROOT=/tmp/agentos-bootstrap-control
Environment=AGENT_DATA_ROOT=$DATA_ROOT
ExecStart=/usr/bin/python3 -m agentos_node.bootstrap_scheduler --role $role --worker-id $worker
Restart=always
RestartSec=2
CPUAccounting=true
MemoryAccounting=true
CPUQuota=$cpu
MemoryHigh=$mem_high
MemoryMax=$mem_max
OOMScoreAdjust=200

[Install]
WantedBy=default.target
EOF
}

write_unit agentos-bootstrap-control.service control oracle-control 100% 2G 4G
write_unit agentos-bootstrap-social-1.service social oracle-social-1 75% 1G 2G
write_unit agentos-bootstrap-social-2.service social oracle-social-2 75% 1G 2G
write_unit agentos-bootstrap-gui.service gui oracle-gui 125% 2G 3G
write_unit agentos-bootstrap-build.service build oracle-build 50% 1G 3G

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

# The marker transfers queue ownership from the legacy scheduler-board hook to
# the role worker pool. Roll back ownership if any worker fails to start.
printf 'source_commit=%s\nenabled_at=%s\n' "$SOURCE_COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER"
rollback_marker=1
trap 'status=$?; if [ "$status" -ne 0 ] && [ "${rollback_marker:-0}" = 1 ]; then rm -f "$MARKER"; fi; rm -rf "$TMP"; exit "$status"' EXIT

systemctl --user daemon-reload
for unit in   agentos-bootstrap-control.service   agentos-bootstrap-social-1.service   agentos-bootstrap-social-2.service   agentos-bootstrap-gui.service   agentos-bootstrap-build.service; do
  systemctl --user enable --now "$unit" >/dev/null
  systemctl --user is-active --quiet "$unit"
  echo "bootstrap_scheduler_unit=$unit:active"
done

for _ in $(seq 1 20); do
  if [ -s "$STATE_ROOT/status.json" ]; then break; fi
  sleep 1
done
test -s "$STATE_ROOT/status.json"
python3 - "$STATE_ROOT/status.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
assert d.get('schema')=='agentos.bootstrap-scheduler-status/v1',d
workers=d.get('workers') or {}
expected={'oracle-control','oracle-social-1','oracle-social-2','oracle-gui','oracle-build'}
missing=expected-set(workers)
assert not missing,missing
print('bootstrap_scheduler_worker_count='+str(len(expected)))
print('bootstrap_scheduler_status=PASS')
PY

rollback_marker=0
echo "bootstrap_scheduler_source_commit=$SOURCE_COMMIT"
echo "bootstrap_scheduler_pool=PASS"
