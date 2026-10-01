#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: legacy Dashboard PM2 retirement must run as ubuntu" >&2
  exit 2
fi

PM2_HOME="${PM2_HOME:-$HOME/.pm2}"
DUMP="$PM2_HOME/dump.pm2"
DAEMON_PID="$(pgrep -f 'PM2 v[0-9].*: God Daemon' | head -n1 || true)"

dashboard_dump_count=0
other_dump_count=0
if [ -f "$DUMP" ]; then
  read -r dashboard_dump_count other_dump_count < <(
    python3 - "$DUMP" <<'PY'
import json
import sys
from pathlib import Path

path=Path(sys.argv[1])
data=json.loads(path.read_text(encoding='utf-8'))
if not isinstance(data,list):
    raise SystemExit('pm2_dump_not_list')
dashboard=0
other=0
for app in data:
    if not isinstance(app,dict):
        other += 1
        continue
    env=app.get('pm2_env') or {}
    fields=[
        str(app.get('name') or ''),
        str(app.get('pm_cwd') or ''),
        str(app.get('pm_exec_path') or ''),
        str(env.get('name') or ''),
        str(env.get('pm_cwd') or ''),
        str(env.get('pm_exec_path') or ''),
    ]
    joined=' '.join(fields).lower()
    if 'agentos-dashboard' in joined or '/agent-data/releases/dashboard/apps/' in joined:
        dashboard += 1
    else:
        other += 1
print(dashboard,other)
PY
  )
fi

dashboard_process_count=0
other_process_count=0
if [ -n "$DAEMON_PID" ]; then
  read -r dashboard_process_count other_process_count < <(
    python3 - "$DAEMON_PID" <<'PY'
from pathlib import Path
import sys

root=int(sys.argv[1])
pp={}
cwd={}
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        pid=int(entry.name)
        status=(entry/'status').read_text(errors='replace')
        parent=0
        for line in status.splitlines():
            if line.startswith('PPid:'):
                parent=int(line.split(':',1)[1].strip())
                break
        pp[pid]=parent
        cwd[pid]=str((entry/'cwd').resolve())
    except Exception:
        pass

def under_root(pid: int) -> bool:
    cur=pid
    seen=set()
    while cur in pp and cur not in seen and cur>1:
        if pp.get(cur)==root:
            return True
        seen.add(cur)
        cur=pp.get(cur,0)
    return False

dashboard=0
other=0
for pid in pp:
    if not under_root(pid):
        continue
    if '/agent-data/releases/dashboard/apps/' in cwd.get(pid,''):
        dashboard += 1
    else:
        other += 1
print(dashboard,other)
PY
  )
fi

echo "dashboard_pm2_dump_apps=$dashboard_dump_count"
echo "dashboard_pm2_other_dump_apps=$other_dump_count"
echo "dashboard_pm2_processes=$dashboard_process_count"
echo "dashboard_pm2_other_processes=$other_process_count"

if [ "$dashboard_dump_count" -eq 0 ] && [ "$dashboard_process_count" -eq 0 ]; then
  echo "dashboard_pm2_registry_retired=ALREADY_ABSENT"
  exit 0
fi

if [ "$other_dump_count" -ne 0 ] || [ "$other_process_count" -ne 0 ]; then
  echo "ERROR: PM2 manages non-Dashboard workload; refusing daemon-level retirement" >&2
  exit 8
fi

if [ ! -f "$DUMP" ]; then
  echo "ERROR: PM2 Dashboard is live but durable dump.pm2 is missing; refusing unbounded retirement" >&2
  exit 9
fi

mkdir -p "$PM2_HOME"
digest="$(sha256sum "$DUMP" | awk '{print $1}')"
backup="$PM2_HOME/dump.pm2.pre-agentos-dashboard-${digest:0:16}.bak"
if [ -e "$backup" ]; then
  test "$(sha256sum "$backup" | awk '{print $1}')" = "$digest" || {
    echo "ERROR: PM2 dump backup collision" >&2
    exit 10
  }
else
  cp "$DUMP" "$backup"
  chmod 0600 "$backup" || true
fi

tmp="$PM2_HOME/.dump.pm2.agentos-dashboard.tmp"
printf '[]\n' > "$tmp"
chmod 0600 "$tmp"
mv "$tmp" "$DUMP"
echo "dashboard_pm2_dump_backup=$backup"
echo "dashboard_pm2_dump_cleared=PASS"

if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
  kill -TERM "$DAEMON_PID"
  for _ in $(seq 1 20); do
    kill -0 "$DAEMON_PID" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$DAEMON_PID" 2>/dev/null; then
    echo "ERROR: PM2 daemon did not terminate after registry retirement" >&2
    exit 11
  fi
fi

# A startup supervisor may relaunch an empty PM2 daemon. That is acceptable,
# but no legacy Dashboard child may return.
sleep 1
if python3 - <<'PY'
from pathlib import Path
import sys
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        cwd=str((entry/'cwd').resolve())
    except Exception:
        continue
    if '/agent-data/releases/dashboard/apps/' in cwd:
        raise SystemExit(1)
raise SystemExit(0)
PY
then
  echo "dashboard_pm2_legacy_processes_absent=PASS"
else
  echo "ERROR: legacy Dashboard process survived PM2 registry retirement" >&2
  exit 12
fi

echo "dashboard_pm2_registry_retired=PASS"
