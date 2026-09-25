#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="${1:?source sha required}"
RUN_ID="${2:?run id required}"
SOURCE_ROOT="${3:?source root required}"

[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$RUN_ID" =~ ^[0-9]+$ ]]
test -d "$SOURCE_ROOT/dashboard"

APP_NAME="agentos-dashboard"
LEGACY="/home/ubuntu/agentmanager/dashboard"
RELEASE_ROOT="/home/ubuntu/agent-data/releases/dashboard/apps"
RUNTIME_ROOT="/home/ubuntu/agent-data/runtime/dashboard"
LIVE="$RUNTIME_ROOT/current"
BACKUP="/home/ubuntu/agent-data/releases/dashboard/migrations/$RUN_ID"
CONFIG_DIR="/home/ubuntu/.config/milkcat"
CONFIG="$CONFIG_DIR/dashboard.env.local"
RELEASE="$RELEASE_ROOT/$SOURCE_SHA-$RUN_ID"
STAGE="$SOURCE_ROOT/dashboard"
TMP="$(mktemp -d /tmp/dashboard-runtime-controller-XXXXXXXX)"

PM2_CLI=""
CURRENT_CWD=""
PREV_LIVE=""
CURRENT_LISTENER=""
CANARY_PID=""
SWITCHED=0
PM2_REPLACED=0
LEGACY_NEXT_MOVED=0
LEGACY_PROBE="$LEGACY/.next.runtime-isolation-probe-$RUN_ID"

listener_pid() {
  local pids
  pids="$(ss -H -ltnp 'sport = :3000' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true)"
  [[ "$pids" =~ ^[0-9]+$ ]] || return 1
  printf '%s' "$pids"
}

port_3000_clear() {
  ! ss -H -ltn 'sport = :3000' | grep -q LISTEN
}

assert_dashboard_listener() {
  local pid="$1"
  local expected="$2"
  [[ "$pid" =~ ^[0-9]+$ ]]
  test "$(readlink -f "/proc/$pid/cwd")" = "$(readlink -f "$expected")"
  ps -p "$pid" -o args= | grep -Fq 'next-server'
}

wait_port_clear() {
  for _ in $(seq 1 20); do
    if port_3000_clear; then return 0; fi
    sleep 1
  done
  return 1
}

wait_dashboard_ready() {
  for _ in $(seq 1 24); do
    if curl --noproxy '*' -fsS --connect-timeout 3 --max-time 8       http://127.0.0.1:3000/dashboard/api/auth/session -o /dev/null 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

pm2_json() {
  node "$PM2_CLI" jlist > "$TMP/pm2.json"
}

pm2_cwd_for_name() {
  pm2_json
  python3 - "$TMP/pm2.json" "$APP_NAME" <<'PY'
import json,sys
apps=json.load(open(sys.argv[1],encoding='utf8'))
rows=[a for a in apps if a.get('name')==sys.argv[2]]
assert len(rows)==1, f'pm2_target_count={len(rows)}'
print((rows[0].get('pm2_env') or {}).get('pm_cwd') or '')
PY
}

pm2_safe_preflight() {
  pm2_json
  python3 - "$TMP/pm2.json" "$APP_NAME" <<'PY'
import json,sys
apps=json.load(open(sys.argv[1],encoding='utf8'))
rows=[a for a in apps if a.get('name')==sys.argv[2]]
assert len(rows)==1, f'dashboard_pm2_target_count={len(rows)}'
app=rows[0]; env=app.get('pm2_env') or {}
script=str(env.get('pm_exec_path') or '')
cwd=str(env.get('pm_cwd') or '')
args=env.get('args')
status=str(env.get('status') or '')
assert cwd.startswith('/home/ubuntu/'), f'dashboard_pm2_cwd_unexpected:{cwd}'
assert script in {'/usr/bin/npm','/usr/local/bin/npm'} or script.endswith('/npm'), f'dashboard_pm2_script_unexpected:{script}'
assert status=='online', f'dashboard_pm2_not_online:{status}'
print('dashboard_pm2_preflight=PASS name='+str(app.get('name'))+' cwd='+cwd+' script=npm')
print(cwd)
PY
}

check_route() {
  local route="$1" expected="$2"
  local code=""
  for attempt in $(seq 1 18); do
    code="$(curl --noproxy '*' -k -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 12       --resolve studio.milkcat.org:443:127.0.0.1 "https://studio.milkcat.org$route" || true)"
    if [ "$code" = "$expected" ]; then
      printf 'dashboard_route=%s status=%s expected=%s ready_after_attempt=%s\n' "$route" "$code" "$expected" "$attempt"
      return 0
    fi
    [ "$attempt" -eq 18 ] || sleep 2
  done
  printf 'dashboard_route=%s status=%s expected=%s readiness=FAILED\n' "$route" "$code" "$expected"
  return 1
}

check_public() {
  local route="$1" expected="$2"
  local code
  code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 15     "https://studio.milkcat.org$route")"
  printf 'dashboard_public_route=%s status=%s expected=%s\n' "$route" "$code" "$expected"
  test "$code" = "$expected"
}

restore_old_runtime() {
  echo 'dashboard_runtime_rollback=STARTED'

  if [ "$LEGACY_NEXT_MOVED" -eq 1 ] && [ -d "$LEGACY_PROBE" ]; then
    mv "$LEGACY_PROBE" "$LEGACY/.next"
    LEGACY_NEXT_MOVED=0
  fi

  node "$PM2_CLI" stop "$APP_NAME" >/dev/null 2>&1 || true
  local current
  current="$(listener_pid || true)"
  if [ -n "$current" ]; then
    if [ -n "$RELEASE" ] && assert_dashboard_listener "$current" "$RELEASE"; then
      kill -TERM "$current" 2>/dev/null || true
    else
      echo 'dashboard_rollback_listener=UNVERIFIED_REFUSING_KILL'
    fi
  fi
  wait_port_clear || true
  node "$PM2_CLI" delete "$APP_NAME" >/dev/null 2>&1 || true

  if [ -n "$PREV_LIVE" ] && [ -d "$PREV_LIVE" ]; then
    ln -sfn "$PREV_LIVE" "$RUNTIME_ROOT/.rollback-$RUN_ID"
    mv -Tf "$RUNTIME_ROOT/.rollback-$RUN_ID" "$LIVE"
  else
    rm -f "$LIVE"
  fi

  if [ -n "$CURRENT_CWD" ] && [ -d "$CURRENT_CWD" ]; then
    if [ ! -f "$CURRENT_CWD/.env.local" ] && [ -f "$CONFIG" ]; then
      cp "$CONFIG" "$CURRENT_CWD/.env.local"
      chmod 600 "$CURRENT_CWD/.env.local"
    fi
    node "$PM2_CLI" start /usr/bin/npm --name "$APP_NAME" --cwd "$CURRENT_CWD" -- start >/dev/null || true
    node "$PM2_CLI" save --force >/dev/null 2>&1 || node "$PM2_CLI" save >/dev/null 2>&1 || true
    if wait_dashboard_ready; then
      echo "dashboard_runtime_rollback=RESTORED cwd=$CURRENT_CWD"
    else
      echo 'dashboard_runtime_rollback=RESTORE_UNVERIFIED'
    fi
  else
    echo 'dashboard_runtime_rollback=OLD_CWD_MISSING'
  fi
}

finish() {
  rc=$?
  trap - EXIT
  if [ -n "$CANARY_PID" ]; then
    kill "$CANARY_PID" 2>/dev/null || true
    wait "$CANARY_PID" 2>/dev/null || true
  fi
  if [ "$rc" -ne 0 ] && [ "$SWITCHED" -eq 1 ]; then
    restore_old_runtime
  elif [ "$LEGACY_NEXT_MOVED" -eq 1 ] && [ -d "$LEGACY_PROBE" ]; then
    mv "$LEGACY_PROBE" "$LEGACY/.next"
  fi
  rm -rf "$TMP"
  exit "$rc"
}
trap finish EXIT

# Service-owned runtime/release roots. The shared checkout is not runtime authority.
sudo -n install -d -m 0750 -o "$(id -u)" -g "$(id -g)" "$RELEASE_ROOT" "$RUNTIME_ROOT" "$BACKUP"
mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

# Resolve a compatible PM2 client without changing global packages.
export PM2_HOME=/home/ubuntu/.pm2
test -S "$PM2_HOME/rpc.sock"
for candidate in /home/ubuntu/.npm/_npx/*/node_modules/pm2/bin/pm2; do
  test -f "$candidate" || continue
  pkg="${candidate%/bin/pm2}/package.json"
  test -f "$pkg" || continue
  version="$(node -p 'require(process.argv[1]).version' "$pkg")"
  if [ "$version" = '7.0.1' ]; then PM2_CLI="$candidate"; break; fi
done
if [ -z "$PM2_CLI" ]; then
  npm install --prefix "$TMP/pm2-client" --ignore-scripts --no-audit --no-fund pm2@7.0.1 >/dev/null
  PM2_CLI="$TMP/pm2-client/node_modules/pm2/bin/pm2"
fi
test -f "$PM2_CLI"

# Read the actual existing runtime before any mutation.
pm2_safe_preflight > "$TMP/pm2-preflight.txt"
cat "$TMP/pm2-preflight.txt"
CURRENT_CWD="$(tail -n 1 "$TMP/pm2-preflight.txt")"
test -d "$CURRENT_CWD"
CURRENT_LISTENER="$(listener_pid)"
assert_dashboard_listener "$CURRENT_LISTENER" "$CURRENT_CWD"
curl --noproxy '*' -fsS --connect-timeout 3 --max-time 10   http://127.0.0.1:3000/dashboard/api/auth/session -o /dev/null
echo "dashboard_runtime_preflight=PASS listener=$CURRENT_LISTENER"

PREV_LIVE="$(readlink -f "$LIVE" 2>/dev/null || true)"

# Migrate secrets/config once out of the mutable checkout. Never print values.
if [ ! -f "$CONFIG" ]; then
  test -f "$CURRENT_CWD/.env.local" || {
    echo 'dashboard_runtime_config=MISSING'
    exit 2
  }
  cp "$CURRENT_CWD/.env.local" "$CONFIG.tmp-$RUN_ID"
  chmod 600 "$CONFIG.tmp-$RUN_ID"
  mv "$CONFIG.tmp-$RUN_ID" "$CONFIG"
fi
test -f "$CONFIG" && test ! -L "$CONFIG"
test "$(stat -c '%u' "$CONFIG")" = "$(id -u)"
chmod 600 "$CONFIG"
python3 - "$CONFIG" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
keys=set()
for raw in p.read_text(encoding='utf8').splitlines():
    line=raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    keys.add(line.split('=',1)[0].strip())
required={'JWT_SECRET','GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET'}
missing=sorted(required-keys)
assert not missing, 'dashboard_runtime_config_missing_keys:'+','.join(missing)
print('dashboard_runtime_config=PASS canonical_private_file=1')
PY

# Build exact source generation in isolation, with the canonical private config.
test "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" = "$SOURCE_SHA"
test -f "$STAGE/app/admin/usage/page.tsx"
test -f "$STAGE/app/api/admin/usage/route.ts"
cp "$CONFIG" "$STAGE/.env.local"
chmod 600 "$STAGE/.env.local"

cd "$STAGE"
npm ci --ignore-scripts --no-audit --no-fund
npm run build
test -f .next/server/app-paths-manifest.json
node -e 'const p=require("./.next/server/app-paths-manifest.json"); for(const r of ["/admin/usage/page","/api/admin/usage/route","/api/auth/session/route"]) if(!p[r]) throw Error("missing built route: "+r); console.log("dashboard_built_routes=PASS");'

# Promote build output as a new immutable release directory.
test ! -e "$RELEASE"
mv "$STAGE" "$RELEASE"
test -f "$RELEASE/.next/server/app-paths-manifest.json"
test -f "$RELEASE/.env.local"
chmod 600 "$RELEASE/.env.local"
printf 'source_sha=%s\nrun_id=%s\nstate=candidate\n' "$SOURCE_SHA" "$RUN_ID" > "$RELEASE/RELEASE_RECEIPT"

# Canary the exact release before switching PM2.
if ss -ltn 'sport = :3099' | grep -q LISTEN; then
  echo 'dashboard_canary_port_in_use=REFUSED'
  exit 2
fi
(
  cd "$RELEASE"
  ./node_modules/.bin/next start -H 127.0.0.1 -p 3099 > "$TMP/canary.log" 2>&1 &
  echo $! > "$TMP/canary.pid"
)
CANARY_PID="$(cat "$TMP/canary.pid")"
canary_ready=0
for _ in $(seq 1 20); do
  code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 8     http://127.0.0.1:3099/dashboard/api/admin/usage 2>/dev/null || true)"
  if [ "$code" = 401 ]; then canary_ready=1; break; fi
  sleep 2
done
test "$canary_ready" -eq 1 || { echo "dashboard_isolated_canary=FAIL code=$code"; exit 1; }
echo 'dashboard_isolated_canary=PASS code=401'
kill "$CANARY_PID" 2>/dev/null || true
wait "$CANARY_PID" 2>/dev/null || true
CANARY_PID=""

# Atomically select the new service release before replacing the PM2 app.
ln -sfn "$RELEASE" "$RUNTIME_ROOT/.candidate-$RUN_ID"
mv -Tf "$RUNTIME_ROOT/.candidate-$RUN_ID" "$LIVE"
SWITCHED=1
test "$(readlink -f "$LIVE")" = "$RELEASE"
echo "dashboard_live_pointer=PASS release=$RELEASE"

# Stop exactly the verified old Dashboard process. Its Next child may outlive PM2 stop.
node "$PM2_CLI" stop "$APP_NAME" >/dev/null
remaining="$(listener_pid || true)"
if [ -n "$remaining" ]; then
  test "$remaining" = "$CURRENT_LISTENER" || {
    echo 'dashboard_listener_changed_unexpectedly=REFUSED'
    exit 2
  }
  assert_dashboard_listener "$remaining" "$CURRENT_CWD" || {
    echo 'dashboard_listener_ownership_changed=REFUSED'
    exit 2
  }
  kill -TERM "$remaining"
fi
wait_port_clear || { echo 'dashboard_old_listener_stop=FAILED'; exit 1; }
node "$PM2_CLI" delete "$APP_NAME" >/dev/null
PM2_REPLACED=1

# Recreate the app against the immutable release, not the shared checkout.
node "$PM2_CLI" start /usr/bin/npm --name "$APP_NAME" --cwd "$RELEASE" -- start >/dev/null
node "$PM2_CLI" save --force >/dev/null 2>&1 || node "$PM2_CLI" save >/dev/null

wait_dashboard_ready || { echo 'dashboard_new_runtime=NOT_READY'; exit 1; }
NEW_LISTENER="$(listener_pid)"
assert_dashboard_listener "$NEW_LISTENER" "$RELEASE"
test "$NEW_LISTENER" != "$CURRENT_LISTENER"

NEW_PM2_CWD="$(pm2_cwd_for_name)"
test "$(readlink -f "$NEW_PM2_CWD")" = "$RELEASE"
test "$(readlink -f "$LIVE")" = "$RELEASE"
echo "dashboard_runtime_isolation=PASS listener=$NEW_LISTENER pm2_cwd=$NEW_PM2_CWD"

# Public/auth route acceptance.
check_route /dashboard/api/auth/session 200
check_route /dashboard/api/admin/usage 401
check_route /dashboard/admin/usage 307
check_route /dashboard/ 308

curl --noproxy '*' -k -sS -D "$TMP/headers" -o /dev/null   --resolve studio.milkcat.org:443:127.0.0.1   https://studio.milkcat.org/dashboard/admin/usage
node - "$TMP/headers" <<'NODE'
const fs=require('node:fs');
const raw=fs.readFileSync(process.argv[2],'utf8');
const match=raw.match(/^location:\s*(.+?)\r?$/im);
if(!match) throw Error('dashboard_signin_redirect_location_missing');
const target=new URL(match[1].trim(),'https://studio.milkcat.org');
if(target.origin!=='https://studio.milkcat.org' ||
   target.pathname!=='/dashboard/api/auth/signin/google' ||
   target.searchParams.get('returnTo')!=='/dashboard/admin/usage') {
  throw Error('dashboard_signin_redirect_destination_invalid');
}
console.log('dashboard_signin_redirect=PASS');
NODE

check_public /dashboard/api/auth/session 200
check_public /dashboard/api/admin/usage 401
check_public /dashboard/admin/usage 307

# Verify the same Unix identity still has access to private analytics credentials.
python3 - <<'PY'
import json, pathlib, stat, urllib.request
home=pathlib.Path('/home/ubuntu')
checks=[
    ('fengshui', home/'.config/milkcat/fengshui-analytics-token',
     'http://127.0.0.1:8868/fengshui/api/analytics/summary?days=30', 'x-analytics-token'),
    ('tarot', home/'.config/milkcat/leopardcat-analytics-token',
     'http://127.0.0.1:8088/api/v1/analytics/summary?days=30', 'x-analytics-token'),
]
for name,path,url,header in checks:
    s=path.lstat()
    assert stat.S_ISREG(s.st_mode) and not stat.S_ISLNK(s.st_mode)
    assert s.st_uid==__import__('os').getuid() and (s.st_mode & 0o077)==0
    token=path.read_text(encoding='utf8').strip()
    assert len(token)>=32
    req=urllib.request.Request(url,headers={header:token})
    with urllib.request.urlopen(req,timeout=8) as resp:
        payload=json.load(resp)
        assert resp.status==200 and isinstance(payload,dict)
    print('dashboard_private_'+name+'_summary=PASS')
PY

# Regression proof for the exact old failure mode:
# temporarily remove only the legacy shared checkout build. Production must stay healthy.
test -d "$LEGACY/.next"
test ! -e "$LEGACY_PROBE"
mv "$LEGACY/.next" "$LEGACY_PROBE"
LEGACY_NEXT_MOVED=1
check_public /dashboard/api/auth/session 200
check_public /dashboard/api/admin/usage 401
check_public /dashboard/admin/usage 307
mv "$LEGACY_PROBE" "$LEGACY/.next"
LEGACY_NEXT_MOVED=0
echo 'dashboard_shared_build_independence=PASS legacy_next_temporarily_absent=1'

printf 'source_sha=%s\nrun_id=%s\nrelease=%s\nlive_pointer=%s\nold_cwd=%s\nnew_cwd=%s\nshared_build_independence=pass\nstatus=PASS\n'   "$SOURCE_SHA" "$RUN_ID" "$RELEASE" "$LIVE" "$CURRENT_CWD" "$RELEASE" > "$BACKUP/receipt.txt"
printf 'source_sha=%s\nrun_id=%s\nstate=active\nshared_build_independence=pass\n'   "$SOURCE_SHA" "$RUN_ID" > "$RELEASE/RELEASE_RECEIPT"

echo "dashboard_immutable_runtime=PASS source_sha=$SOURCE_SHA release=$RELEASE"
