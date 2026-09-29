#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
DASH="$REPO/dashboard"
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

git -C "$REPO" fetch origin "$SOURCE_COMMIT"
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"

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

  # Retire legacy dashboard processes before the canonical systemd-owned
  # runtime starts. A reboot may leave none; that is a valid cold-start case.
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
    if cwd != target:
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
