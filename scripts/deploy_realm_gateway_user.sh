#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
DASH="$REPO/dashboard"
PORT_MANAGER_REL="scripts/core_services/port_manager.py"
PORT_MANAGER_EXACT="/tmp/agentos-port-manager-$SOURCE_COMMIT.py"
RETIRE_PM2_REL="scripts/retire_legacy_dashboard_pm2_user.sh"
RETIRE_PM2_EXACT="/tmp/agentos-retire-dashboard-pm2-$SOURCE_COMMIT.sh"
ROUTE_REL='dashboard/app/api/agentos/[...path]/route.ts'
ROUTE="$REPO/$ROUTE_REL"
PUBLIC='https://studio.milkcat.org/dashboard/api/agentos/v1/health'
PUBLIC_BOOTSTRAP='https://studio.milkcat.org/dashboard/api/agentos/v1/bootstrap?node_id=__gateway_probe__'
LOCAL='http://127.0.0.1:8780/v1/health'
LOCAL_GATEWAY='http://127.0.0.1:3000/dashboard/api/agentos/v1/health'
LOCAL_GATEWAY_BOOTSTRAP='http://127.0.0.1:3000/dashboard/api/agentos/v1/bootstrap?node_id=__gateway_probe__'

[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'ERROR: AGENTOS_SOURCE_COMMIT must be exact lowercase 40-hex commit' >&2; exit 2; }
[ -d "$REPO/.git" ] || { echo "ERROR: repo missing" >&2; exit 2; }
[ -f "$DASH/package.json" ] || { echo "ERROR: dashboard missing" >&2; exit 2; }

# Fetch the exact source revision before invoking any deployment dependency.
# Governance helpers must come from the same immutable revision as the repair.
git -C "$REPO" fetch origin "$SOURCE_COMMIT"
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
git -C "$REPO" show "$SOURCE_COMMIT:$PORT_MANAGER_REL" > "$PORT_MANAGER_EXACT"
chmod 700 "$PORT_MANAGER_EXACT"
echo "port_manager_source=$SOURCE_COMMIT:$PORT_MANAGER_REL"
git -C "$REPO" show "$SOURCE_COMMIT:$RETIRE_PM2_REL" > "$RETIRE_PM2_EXACT"
chmod 700 "$RETIRE_PM2_EXACT"
echo "dashboard_pm2_retire_source=$SOURCE_COMMIT:$RETIRE_PM2_REL"

PORT_3000_OWNER="$(
  python3 "$PORT_MANAGER_EXACT" list --json |
    python3 -c 'import json,sys; print((json.load(sys.stdin).get("3000") or {}).get("project") or "")'
)"
case "$PORT_3000_OWNER" in
  agentos-dashboard)
    python3 "$PORT_MANAGER_EXACT" require 3000 agentos-dashboard
    ;;
  agentmanager)
    python3 "$PORT_MANAGER_EXACT" migrate 3000 agentmanager agentos-dashboard --desc "AgentOS Dashboard / Realm Gateway"
    ;;
  "")
    python3 "$PORT_MANAGER_EXACT" ensure 3000 agentos-dashboard --desc "AgentOS Dashboard / Realm Gateway"
    ;;
  *)
    echo "ERROR: governed port 3000 belongs to unexpected project '$PORT_3000_OWNER'" >&2
    exit 8
    ;;
esac
python3 "$PORT_MANAGER_EXACT" require 3000 agentos-dashboard
python3 "$PORT_MANAGER_EXACT" ensure 8780 agentos-realm-fabric --desc "AgentOS ONE Realm Fabric"
echo "port_governance=PASS"

# Serialize all Dashboard mutations. Multiple repair/deploy carriers touching the
# same .next tree caused transient ENOENT build failures and ambiguous runtime state.
command -v flock >/dev/null 2>&1 || { echo "ERROR: flock is required for dashboard deployment serialization" >&2; exit 2; }
exec 9>/tmp/agentos-dashboard-deploy.lock
flock -w 180 9 || { echo "ERROR: another dashboard deployment owns the mutation lock" >&2; exit 7; }
echo "dashboard_deploy_lock=PASS"

DASH_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
DASH_UNIT="$DASH_UNIT_DIR/agentos-dashboard.service"

install_dashboard_service() {
  mkdir -p "$DASH_UNIT_DIR"
  local npm_bin
  npm_bin="$(command -v npm)"
  [ -n "$npm_bin" ] || { echo "ERROR: npm missing" >&2; return 4; }

  cat > "$DASH_UNIT" <<EOF
[Unit]
Description=AgentOS Dashboard / Realm Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DASH
Environment=NODE_ENV=production
Environment=PORT=3000
ExecStart=$npm_bin start
Restart=always
RestartSec=5
KillMode=control-group
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable agentos-dashboard.service >/dev/null
  echo "dashboard_service_install=PASS"
}

restart_dashboard() {
  install_dashboard_service

  # Retire any PM2-owned legacy dashboard release before the canonical
  # systemd-owned runtime starts. Killing only the child process is insufficient
  # because PM2 immediately resurrects it and keeps port 3000 occupied.
  PM2_BIN="$(command -v pm2 2>/dev/null || true)"
  if [ -z "$PM2_BIN" ] && [ -d "$HOME/.nvm/versions/node" ]; then
    PM2_BIN="$(find "$HOME/.nvm/versions/node" -type f -path '*/bin/pm2' -perm -u+x 2>/dev/null | sort | tail -n1 || true)"
  fi
  if [ -z "$PM2_BIN" ]; then
    PM2_BIN="$(find "$HOME/.local" /usr/local -type f -path '*/bin/pm2' -perm -u+x 2>/dev/null | sort | tail -n1 || true)"
  fi
  echo "dashboard_pm2_cli=${PM2_BIN:-MISSING}"
  if [ -n "$PM2_BIN" ]; then
    "$PM2_BIN" jlist > /tmp/agentos-pm2-jlist.json 2>/dev/null || echo '[]' > /tmp/agentos-pm2-jlist.json
    echo "dashboard_pm2_inventory_begin"
    python3 - <<'PY'
import json
from pathlib import Path
try:
    data=json.loads(Path('/tmp/agentos-pm2-jlist.json').read_text())
except Exception:
    data=[]
for app in data:
    env=app.get('pm2_env') or {}
    print('pm_id=%s name=%s cwd=%s pm_exec_path=%s status=%s' % (
        app.get('pm_id'),
        app.get('name') or env.get('name'),
        env.get('pm_cwd'),
        env.get('pm_exec_path'),
        env.get('status'),
    ))
PY
    echo "dashboard_pm2_inventory_end"

    mapfile -t legacy_pm2_ids < <(
      python3 - <<'PY'
import json
from pathlib import Path
try:
    data=json.loads(Path('/tmp/agentos-pm2-jlist.json').read_text())
except Exception:
    data=[]
for app in data:
    env=app.get('pm2_env') or {}
    fields=[
        str(env.get('pm_cwd') or ''),
        str(env.get('pm_exec_path') or ''),
        str(app.get('name') or ''),
        str(env.get('name') or ''),
    ]
    joined=' '.join(fields).lower()
    if '/agent-data/releases/dashboard/apps/' in joined or 'dashboard' in joined:
        ident=app.get('pm_id')
        if ident is not None:
            print(ident)
PY
    )
    if [ "${#legacy_pm2_ids[@]}" -gt 0 ]; then
      echo "dashboard_legacy_pm2_ids=${legacy_pm2_ids[*]}"
      "$PM2_BIN" delete "${legacy_pm2_ids[@]}"
      "$PM2_BIN" save --force >/dev/null
      echo "dashboard_legacy_pm2_retired=PASS"
    else
      echo "dashboard_legacy_pm2_retired=NO_MATCH"
    fi
  fi

  # If the PM2 CLI is unavailable, retire the daemon only after proving both
  # its durable registry and all descendants are Dashboard-only. This helper is
  # idempotent and becomes a no-op when the Dashboard has already been removed.
  "$RETIRE_PM2_EXACT"

  # Retire any remaining legacy dashboard processes before the canonical
  # systemd-owned runtime starts. A reboot may leave none; that is valid.
  local own_pgid
  own_pgid=$(ps -o pgid= -p $$ | tr -d ' ')
  python3 - "$DASH" "$own_pgid" <<'PY'
from pathlib import Path
import os,signal,sys,time
target=str(Path(sys.argv[1]).resolve())
own_pgid=int(sys.argv[2])
groups=set()
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        if entry.stat().st_uid != os.getuid():
            continue
        cwd=str((entry/'cwd').resolve())
        raw=(entry/'cmdline').read_bytes().replace(b'\0',b' ').decode('utf-8','replace').strip()
        pgid=os.getpgid(int(entry.name))
    except (OSError, PermissionError, ProcessLookupError):
        continue
    is_dashboard_runtime = (
        cwd == target
        or '/agent-data/releases/dashboard/apps/' in cwd
    )
    if not is_dashboard_runtime:
        continue
    if raw.startswith('npm start') or 'next start' in raw or raw.startswith('next-server'):
        if pgid != own_pgid:
            groups.add(pgid)
for pgid in sorted(groups):
    try:
        os.killpg(pgid, signal.SIGTERM)
        print(f'dashboard_legacy_term_pgid={pgid}')
    except ProcessLookupError:
        pass
if groups:
    time.sleep(2)
PY

  systemctl --user restart agentos-dashboard.service
  for i in $(seq 1 30); do
    if systemctl --user is-active --quiet agentos-dashboard.service &&        curl -fsS --max-time 2 http://127.0.0.1:3000/dashboard >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  systemctl --user is-active --quiet agentos-dashboard.service || {
    systemctl --user --no-pager --full status agentos-dashboard.service >&2 || true
    journalctl --user -u agentos-dashboard.service -n 80 --no-pager >&2 || true
    return 4
  }
  curl -fsS --max-time 3 http://127.0.0.1:3000/dashboard >/dev/null
  echo "dashboard_service_active=PASS"
  echo "dashboard_cold_start_supported=PASS"

  echo "dashboard_runtime_identity_begin"
  systemctl --user show agentos-dashboard.service -p MainPID -p ExecMainPID -p ActiveState -p SubState -p FragmentPath --no-pager || true
  ss -ltnp 2>/dev/null | grep ':3000' || true
  python3 - <<'PY'
from pathlib import Path
import os
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        pid=int(entry.name)
        cmd=(entry/'cmdline').read_bytes().replace(b'\0',b' ').decode('utf-8','replace').strip()
        cwd=str((entry/'cwd').resolve())
        status=(entry/'status').read_text(errors='replace')
        if 'node' not in cmd and 'next' not in cmd and 'npm' not in cmd:
            continue
        uid_line=next((x for x in status.splitlines() if x.startswith('Uid:')), '')
        print(f'pid={pid} cwd={cwd} uid={uid_line} cmd={cmd[:500]}')
    except Exception:
        pass
PY
  echo "dashboard_runtime_identity_end"

  echo "dashboard_release_supervisor_identity_begin"
  python3 - <<'PY'
from pathlib import Path
import os
def read_text(p):
    try: return p.read_text(errors='replace')
    except Exception: return ''
for entry in Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        pid=int(entry.name)
        cwd=str((entry/'cwd').resolve())
        cmd=(entry/'cmdline').read_bytes().replace(b'\0',b' ').decode('utf-8','replace').strip()
    except Exception:
        continue
    if '/agent-data/releases/dashboard/apps/' not in cwd:
        continue
    status=read_text(entry/'status')
    ppid=''
    for line in status.splitlines():
        if line.startswith('PPid:'):
            ppid=line.split(':',1)[1].strip()
            break
    cgroup=read_text(entry/'cgroup').strip().replace('\n',' | ')
    print(f'pid={pid} ppid={ppid} cwd={cwd} cgroup={cgroup} cmd={cmd[:500]}')
    seen=set()
    cur=pid
    depth=0
    while depth < 8:
        if cur in seen: break
        seen.add(cur)
        st=read_text(Path('/proc')/str(cur)/'status')
        parent=0
        for line in st.splitlines():
            if line.startswith('PPid:'):
                try: parent=int(line.split(':',1)[1].strip())
                except Exception: parent=0
                break
        if parent <= 1: break
        try:
            pcmd=(Path('/proc')/str(parent)/'cmdline').read_bytes().replace(b'\0',b' ').decode('utf-8','replace').strip()
            pcg=read_text(Path('/proc')/str(parent)/'cgroup').strip().replace('\n',' | ')
            print(f'  parent pid={parent} cgroup={pcg} cmd={pcmd[:500]}')
        except Exception:
            pass
        cur=parent
        depth += 1
PY
  systemctl --user list-units --type=service --all --no-pager | grep -Ei 'dashboard|studio|release' || true
  echo "dashboard_release_supervisor_identity_end"
}

TMP=$(mktemp -d)
BACKUP="$TMP/route.backup"
HAD_ROUTE=0
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

if [ -f "$ROUTE" ]; then
  cp "$ROUTE" "$BACKUP"
  HAD_ROUTE=1
fi

rollback() {
  set +e
  if [ "$HAD_ROUTE" = 1 ]; then
    mkdir -p "$(dirname "$ROUTE")"
    cp "$BACKUP" "$ROUTE"
  else
    rm -f "$ROUTE"
  fi
  (cd "$DASH" && npm run build >/tmp/agentos-realm-gateway-rollback-build.log 2>&1)
  restart_dashboard >/tmp/agentos-realm-gateway-rollback-restart.log 2>&1 || true
  set -e
}

trap 'rc=$?; if [ $rc -ne 0 ]; then rollback; fi; cleanup; exit $rc' EXIT

mkdir -p "$(dirname "$ROUTE")"
git -C "$REPO" show "$SOURCE_COMMIT:$ROUTE_REL" > "$ROUTE"
chmod 0664 "$ROUTE" || true

echo "route_source=$SOURCE_COMMIT:$ROUTE_REL"
python3 - "$ROUTE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
required=['127.0.0.1:8780','/v1/bootstrap','/v1/join/request','/v1/join/claim','/v1/heartbeat','x-agentos-realm-gateway']
missing=[x for x in required if x not in s]
assert not missing, missing
assert 'http://' + '${' not in s
print('route_guard=PASS')
PY

LOCAL_BODY=""
for i in $(seq 1 12); do
  LOCAL_BODY=$(curl -fsS --max-time 3 "$LOCAL" 2>/dev/null || true)
  if printf '%s' "$LOCAL_BODY" | grep -q 'agentos.one-health/v0.1' && printf '%s' "$LOCAL_BODY" | grep -q 'realm-alston'; then
    break
  fi
  sleep 2
done
if ! printf '%s' "$LOCAL_BODY" | grep -q 'agentos.one-health/v0.1' || ! printf '%s' "$LOCAL_BODY" | grep -q 'realm-alston'; then
  echo "ERROR: local Realm health did not recover" >&2
  systemctl --user list-units --type=service --all --no-pager | grep -Ei 'realm|agentos|one' >&2 || true
  ss -ltnp 2>/dev/null | grep ':8780' >&2 || true
  exit 6
fi
echo "local_realm_health=PASS"

# The canonical systemd runtime must not read the same .next tree while it is
# being destroyed/rebuilt. An explicit stop does not trigger Restart=always.
systemctl --user stop agentos-dashboard.service >/dev/null 2>&1 || true
echo "dashboard_canonical_runtime_stopped_for_build=PASS"

rm -rf "$DASH/.next"
echo "dashboard_build_cache=CLEARED"
(cd "$DASH" && npm run build)
echo "dashboard_build=PASS"

if ! grep -R -q '"method".*"path"\|"path".*"method"' "$DASH/.next/server" 2>/dev/null; then
  echo "ERROR: compiled Realm gateway artifact does not contain current diagnostic fields" >&2
  exit 5
fi
echo "realm_gateway_compiled_generation=PASS"

restart_dashboard

for i in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:3000/dashboard >/dev/null; then break; fi
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:3000/dashboard >/dev/null
echo "dashboard_local=PASS"

LG_BODY=/tmp/agentos-realm-local-gateway
LG_CODE=$(curl -sS -o "$LG_BODY" -w '%{http_code}' --max-time 5 "$LOCAL_GATEWAY" || true)
echo "local_gateway_http=$LG_CODE prefix=$(head -c 240 "$LG_BODY" 2>/dev/null | tr '\n' ' ' | tr '\r' ' ' || true)"
[ "$LG_CODE" = 200 ]
grep -q 'agentos.one-health/v0.1' "$LG_BODY"
grep -q 'realm-alston' "$LG_BODY"
echo "realm_gateway_local=PASS"

# No token is supplied intentionally: a correctly routed bootstrap request must
# reach Realm auth and return 401, never the gateway allowlist 404.
LB_BODY=/tmp/agentos-realm-local-bootstrap
LB_CODE=$(curl -sS -o "$LB_BODY" -w '%{http_code}' --max-time 5 "$LOCAL_GATEWAY_BOOTSTRAP" || true)
echo "local_bootstrap_http=$LB_CODE prefix=$(head -c 240 "$LB_BODY" 2>/dev/null | tr '\n' ' ' | tr '\r' ' ' || true)"
[ "$LB_CODE" = 401 ]
! grep -q 'Realm gateway route not allowlisted' "$LB_BODY"
echo "realm_gateway_bootstrap_local=PASS"

for i in $(seq 1 30); do
  BODY=$(curl -fsS --max-time 5 "$PUBLIC" 2>/dev/null || true)
  if printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1' && printf '%s' "$BODY" | grep -q 'realm-alston'; then break; fi
  sleep 1
done
BODY=$(curl -fsS --max-time 5 "$PUBLIC")
printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1'
printf '%s' "$BODY" | grep -q 'realm-alston'
echo "realm_gateway_public=PASS"

PB_BODY=/tmp/agentos-realm-public-bootstrap
PB_CODE=$(curl -sS -o "$PB_BODY" -w '%{http_code}' --max-time 8 "$PUBLIC_BOOTSTRAP" || true)
echo "public_bootstrap_http=$PB_CODE prefix=$(head -c 240 "$PB_BODY" 2>/dev/null | tr '\n' ' ' | tr '\r' ' ' || true)"
[ "$PB_CODE" = 401 ]
! grep -q 'Realm gateway route not allowlisted' "$PB_BODY"
echo "realm_gateway_bootstrap_public=PASS"

echo "realm_gateway_source_commit=$SOURCE_COMMIT"
echo "realm_gateway_url=https://studio.milkcat.org/dashboard/api/agentos"
echo "nginx_mutation=NONE"
echo "root_privilege=NONE"
