#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
DASH="$REPO/dashboard"
ROUTE_REL='dashboard/app/api/agentos/[...path]/route.ts'
ROUTE="$REPO/$ROUTE_REL"
PUBLIC='https://studio.milkcat.org/dashboard/api/agentos/v1/health'
LOCAL='http://127.0.0.1:8780/v1/health'
LOCAL_GATEWAY='http://127.0.0.1:3000/dashboard/api/agentos/v1/health'

[ -d "$REPO/.git" ] || { echo "ERROR: repo missing" >&2; exit 2; }
[ -f "$DASH/package.json" ] || { echo "ERROR: dashboard missing" >&2; exit 2; }

find_dashboard_runtime() {
  python3 - "$DASH" <<'PY'
from pathlib import Path
import os,sys
root=Path('/proc'); target=str(Path(sys.argv[1]).resolve()); rows=[]
for entry in root.iterdir():
    if not entry.name.isdigit(): continue
    pid=int(entry.name)
    try:
        st=entry.stat()
        if st.st_uid != os.getuid(): continue
        cwd=str((entry/'cwd').resolve())
        raw=(entry/'cmdline').read_bytes().replace(b'\0',b' ').decode('utf-8','replace').strip()
        ppid=None
        for line in (entry/'status').read_text().splitlines():
            if line.startswith('PPid:'):
                ppid=int(line.split()[1]); break
        pgid=os.getpgid(pid)
    except (OSError, PermissionError, ProcessLookupError):
        continue
    if cwd != target: continue
    if raw.startswith('npm start') or 'next start' in raw or raw.startswith('next-server'):
        rows.append((pid, ppid if ppid is not None else -1, pgid, raw))
for pid,ppid,pgid,raw in sorted(rows):
    print(f'{pid}\t{ppid}\t{pgid}\t{raw}')
PY
}

find_dashboard_npm_pid() {
  find_dashboard_runtime | awk -F '\t' '$4 ~ /^npm start/ {print $1}'
}

restart_dashboard() {
  local before groups old_npm new_npm own_pgid
  before=$(find_dashboard_runtime)
  [ -n "$before" ] || { echo "ERROR: no dashboard runtime found" >&2; return 4; }
  echo 'dashboard_runtime_before:'
  printf '%s\n' "$before"

  old_npm=$(printf '%s\n' "$before" | awk -F '\t' '$4 ~ /^npm start/ {print $1}')
  [ "$(printf '%s\n' "$old_npm" | sed '/^$/d' | wc -l)" -eq 1 ] || {
    echo "ERROR: expected exactly one dashboard npm start before restart, got: $old_npm" >&2
    return 4
  }

  groups=$(printf '%s\n' "$before" | awk -F '\t' '{print $3}' | sort -nu)
  [ -n "$groups" ] || { echo "ERROR: no dashboard process groups found" >&2; return 4; }
  own_pgid=$(ps -o pgid= -p $$ | tr -d ' ')
  for pgid in $groups; do
    [ "$pgid" != "$own_pgid" ] || { echo "ERROR: refusing own process group" >&2; return 4; }
    echo "dashboard_term_pgid=$pgid"
    kill -TERM -- "-$pgid" 2>/dev/null || true
  done

  for i in $(seq 1 30); do
    sleep 1
    new_npm=$(find_dashboard_npm_pid 2>/dev/null || true)
    if [ -n "$new_npm" ] && [ "$new_npm" != "$old_npm" ]; then
      break
    fi
  done
  [ -n "${new_npm:-}" ] && [ "$new_npm" != "$old_npm" ] || {
    echo "ERROR: dashboard supervisor did not restart npm start" >&2
    return 4
  }
  echo "dashboard_old_pid=$old_npm"
  echo "dashboard_new_pid=$new_npm"

  for pgid in $groups; do
    if ps -eo pgid= | awk '{print $1}' | grep -qx "$pgid"; then
      echo "ERROR: old dashboard process group still alive: $pgid" >&2
      return 4
    fi
  done
  echo 'dashboard_runtime_after:'
  find_dashboard_runtime
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

git -C "$REPO" fetch origin main
mkdir -p "$(dirname "$ROUTE")"
git -C "$REPO" show "origin/main:$ROUTE_REL" > "$ROUTE"
chmod 0664 "$ROUTE" || true

echo "route_source=origin/main:$ROUTE_REL"
python3 - "$ROUTE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
required=['127.0.0.1:8780','/v1/join/request','/v1/join/claim','/v1/heartbeat','x-agentos-realm-gateway']
missing=[x for x in required if x not in s]
assert not missing, missing
assert 'http://' + '${' not in s
print('route_guard=PASS')
PY

LOCAL_BODY=$(curl -fsS --max-time 3 "$LOCAL")
printf '%s' "$LOCAL_BODY" | grep -q 'agentos.one-health/v0.1'
printf '%s' "$LOCAL_BODY" | grep -q 'realm-alston'
echo "local_realm_health=PASS"

(cd "$DASH" && npm run build)
echo "dashboard_build=PASS"
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

for i in $(seq 1 30); do
  BODY=$(curl -fsS --max-time 5 "$PUBLIC" 2>/dev/null || true)
  if printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1' && printf '%s' "$BODY" | grep -q 'realm-alston'; then break; fi
  sleep 1
done
BODY=$(curl -fsS --max-time 5 "$PUBLIC")
printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1'
printf '%s' "$BODY" | grep -q 'realm-alston'
echo "realm_gateway_public=PASS"
echo "realm_gateway_url=https://studio.milkcat.org/dashboard/api/agentos"
echo "nginx_mutation=NONE"
echo "root_privilege=NONE"
