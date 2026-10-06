#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="${1:?source sha required}"
RUN_ID="${2:?run id required}"
RUN_ATTEMPT="${3:?run attempt required}"

REPO=/home/ubuntu/agentmanager
RELEASE_ROOT=/home/ubuntu/agent-data/releases/dashboard-blue-green
RUNTIME_ROOT=/home/ubuntu/agent-data/runtime/dashboard
BLUE_LINK="$RUNTIME_ROOT/blue"
CONFIG=/home/ubuntu/.config/milkcat/dashboard.env.local
NGINX_SITE=/etc/nginx/sites-enabled/studio.milkcat.org
PORT=3040
UNIT=agentos-dashboard-blue.service
RELEASE="$RELEASE_ROOT/$SOURCE_SHA-$RUN_ID-$RUN_ATTEMPT"

[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$RUN_ID" =~ ^[0-9]+$ ]]
[[ "$RUN_ATTEMPT" =~ ^[0-9]+$ ]]
test -d "$REPO/.git"
test -f "$CONFIG"
test -f "$NGINX_SITE"

exec 9>/tmp/agentos-dashboard-deploy.lock
flock -w 360 9
echo "dashboard_blue_cutover_lock=PASS"

git -C "$REPO" fetch --no-tags origin "$SOURCE_SHA"
git -C "$REPO" cat-file -e "$SOURCE_SHA^{commit}"

mkdir -p "$RELEASE_ROOT" "$RUNTIME_ROOT"
test ! -e "$RELEASE"
mkdir -p "$RELEASE"
git -C "$REPO" archive "$SOURCE_SHA:dashboard" | tar -x -C "$RELEASE"
cp "$CONFIG" "$RELEASE/.env.local"
chmod 600 "$RELEASE/.env.local"

cd "$RELEASE"
npm ci --ignore-scripts --no-audit --no-fund
npm run build
echo "dashboard_blue_build=PASS"

ln -sfn "$RELEASE" "$RUNTIME_ROOT/.blue-candidate-$RUN_ID"
mv -Tf "$RUNTIME_ROOT/.blue-candidate-$RUN_ID" "$BLUE_LINK"

systemctl --user daemon-reload
systemctl --user restart "$UNIT"

ready=0
for _ in $(seq 1 40); do
  session_code=$(curl -sS -o /tmp/dashboard-blue-session -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/dashboard/api/auth/session" || true)
  health_code=$(curl -sS -o /tmp/dashboard-blue-health -w '%{http_code}' --max-time 3 "http://127.0.0.1:$PORT/dashboard/api/agentos/v1/health" || true)
  if [ "$session_code" = 200 ] && [ "$health_code" = 200 ]; then
    ready=1
    break
  fi
  sleep 1
done
test "$ready" = 1
grep -q 'agentos.one-health/v0.1' /tmp/dashboard-blue-health
echo "dashboard_blue_slot_ready=PASS"

PID="$(ss -H -ltnp "sport = :$PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
[[ "$PID" =~ ^[0-9]+$ ]]
CWD="$(readlink -f "/proc/$PID/cwd")"
test "$CWD" = "$RELEASE"
echo "dashboard_blue_slot_identity=PASS"

CURRENT_LINE="$(grep -F 'set $agentos_dashboard_upstream ' "$NGINX_SITE" | head -n1 || true)"
test -n "$CURRENT_LINE"
echo "dashboard_upstream_before=$CURRENT_LINE"

sudo -n cp "$NGINX_SITE" "$NGINX_SITE.pre-blue-cutover-$RUN_ID"
sudo -n python3 - "$NGINX_SITE" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
old='set $agentos_dashboard_upstream http://127.0.0.1:3000;'
new='set $agentos_dashboard_upstream http://127.0.0.1:3040;'
if new in s:
    raise SystemExit(0)
if old not in s:
    raise SystemExit('expected dashboard upstream switch point missing')
p.write_text(s.replace(old,new,1))
PY

sudo -n nginx -t
sudo -n systemctl reload nginx
echo "dashboard_blue_nginx_reload=PASS"

public_ready=0
for _ in $(seq 1 20); do
  code=$(curl -sS -o /tmp/dashboard-public-session -w '%{http_code}' --max-time 5 https://studio.milkcat.org/dashboard/api/auth/session || true)
  if [ "$code" = 200 ]; then
    public_ready=1
    break
  fi
  sleep 0.5
done
test "$public_ready" = 1
echo "dashboard_blue_public_session=PASS"

public_health=$(curl -sS -o /tmp/dashboard-public-health -w '%{http_code}' --max-time 5 https://studio.milkcat.org/dashboard/api/agentos/v1/health || true)
test "$public_health" = 200
grep -q 'agentos.one-health/v0.1' /tmp/dashboard-public-health
echo "dashboard_blue_public_realm=PASS"

grep -Fq 'set $agentos_dashboard_upstream http://127.0.0.1:3040;' "$NGINX_SITE"
printf 'source_sha=%s\nrun_id=%s\nrun_attempt=%s\nslot=blue\nport=%s\nstate=active\nrelease=%s\n'   "$SOURCE_SHA" "$RUN_ID" "$RUN_ATTEMPT" "$PORT" "$RELEASE" > "$RELEASE/RELEASE_RECEIPT"
echo "dashboard_blue_first_cutover=PASS"
