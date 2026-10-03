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
RELEASE_ROOT="$HOME/.local/share/agentos/bootstrap-scheduler"
RELEASE="$RELEASE_ROOT/releases/$SOURCE_COMMIT"
CURRENT="$RELEASE_ROOT/current"

mkdir -p "$UNIT_DIR" "$STATE_ROOT" "$LOCK_ROOT" "$RELEASE_ROOT/releases"
exec 9>"$LOCK_ROOT/oracle-core-runtime.lock"
flock -w 120 9

git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT" >/dev/null
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"

WORK="$(mktemp -d)"
STAGE="$RELEASE_ROOT/.stage-$SOURCE_COMMIT"
rm -rf "$STAGE"
mkdir -p "$STAGE" "$WORK/units"

UNITS=(
  agentos-bootstrap-control.service
  agentos-bootstrap-social-1.service
  agentos-bootstrap-social-2.service
  agentos-bootstrap-gui.service
  agentos-bootstrap-build.service
  agentos-bootstrap-router.service
)

for unit in "${UNITS[@]}"; do
  [ -f "$UNIT_DIR/$unit" ] && cp "$UNIT_DIR/$unit" "$WORK/units/$unit"
done

rollback_marker=1
rollback() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "bootstrap scheduler rollout failed; restoring prior units" >&2
    [ "$rollback_marker" = 1 ] && rm -f "$MARKER"
    for unit in "${UNITS[@]}"; do
      if [ -f "$WORK/units/$unit" ]; then
        cp "$WORK/units/$unit" "$UNIT_DIR/$unit"
      fi
    done
    systemctl --user daemon-reload || true
    for unit in "${UNITS[@]}"; do
      [ -f "$UNIT_DIR/$unit" ] && systemctl --user restart "$unit" || true
    done
  fi
  rm -rf "$WORK" "$STAGE"
  exit "$status"
}
trap rollback EXIT

# Materialize an immutable scheduler generation. Build-role executor providers
# are loaded from this same exact release, so include the full repo-local Python
# dependency closure used by the shared Action Relay registry.
git -C "$REPO" archive "$SOURCE_COMMIT" agentos_node agent_core runtime_core scripts | tar -x -C "$STAGE"
PYTHONPATH="$STAGE" /usr/bin/python3 -m py_compile   "$STAGE/agentos_node/bootstrap_control.py"   "$STAGE/agentos_node/bootstrap_scheduler.py"   "$STAGE/agent_core/realm_fabric.py"

PYTHONPATH="$STAGE" /usr/bin/python3 - <<'PY'
from agent_core.executor_job_contract import canonical_executor_job_request
from agent_core.realm_fabric import RealmFabricStore, ReceiptArchiveStore
from agentos_node.bootstrap_scheduler import policy_for
from agentos_node.executor_job_action_relay import ENGINEERING_SUBAGENT_PROVIDERS_REGISTERED

request = canonical_executor_job_request("engineering.windows-thin-client.fix")
assert request["job_type"] == "engineering.windows-thin-client.fix", request
assert ENGINEERING_SUBAGENT_PROVIDERS_REGISTERED is True
print('bootstrap_scheduler_exact_import=PASS')
print('bootstrap_scheduler_engineering_executor_job=PASS')
PY

rm -rf "$RELEASE"
mv "$STAGE" "$RELEASE"
STAGE="$RELEASE_ROOT/.stage-consumed-$SOURCE_COMMIT"

write_unit() {
  local unit="$1" role="$2" worker="$3" cpu="$4" mem_high="$5" mem_max="$6"
  cat > "$UNIT_DIR/$unit" <<EOF
[Unit]
Description=AgentOS Bootstrap Scheduler Worker $worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$RELEASE
Environment=PYTHONPATH=$RELEASE
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
write_unit agentos-bootstrap-router.service router agentos-router 25% 256M 512M

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"

printf 'source_commit=%s\nenabled_at=%s\nrelease=%s\n'   "$SOURCE_COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RELEASE" > "$MARKER"

systemctl --user daemon-reload
for unit in "${UNITS[@]}"; do
  systemctl --user enable "$unit" >/dev/null
  systemctl --user restart "$unit"
  systemctl --user is-active --quiet "$unit"
  PID="$(systemctl --user show "$unit" -p MainPID --value)"
  test -n "$PID" && test "$PID" != 0
  CWD="$(readlink -f "/proc/$PID/cwd")"
  test "$CWD" = "$RELEASE"
  echo "bootstrap_scheduler_unit=$unit:active:release=$CWD"
done

worker_status_ready=0
for _ in $(seq 1 30); do
  if [ -s "$STATE_ROOT/status.json" ] && python3 -c "import json; d=json.load(open('$STATE_ROOT/status.json',encoding='utf-8')); expected={'oracle-control','oracle-social-1','oracle-social-2','oracle-gui','oracle-build','agentos-router'}; raise SystemExit(0 if expected <= set(d.get('workers') or {}) else 1)"; then
    worker_status_ready=1
    break
  fi
  sleep 1
done
test "$worker_status_ready" = 1

python3 -c "import json; d=json.load(open('$STATE_ROOT/status.json',encoding='utf-8')); assert d.get('schema')=='agentos.bootstrap-scheduler-status/v1',d; expected={'oracle-control','oracle-social-1','oracle-social-2','oracle-gui','oracle-build','agentos-router'}; workers=d.get('workers') or {}; assert expected <= set(workers), expected-set(workers); print('bootstrap_scheduler_worker_count='+str(len(expected))); print('bootstrap_scheduler_status=PASS')"

ln -sfn "$RELEASE" "$CURRENT"
rollback_marker=0
trap - EXIT
rm -rf "$WORK"
echo "bootstrap_scheduler_source_commit=$SOURCE_COMMIT"
echo "bootstrap_scheduler_release=$RELEASE"
echo "bootstrap_scheduler_current=$(readlink -f "$CURRENT")"
echo "bootstrap_scheduler_pool=PASS"
