#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
DASH="$REPO/dashboard"
ROUTE_REL='dashboard/app/agentos/one/[...path]/route.ts'
ROUTE="$REPO/$ROUTE_REL"
PUBLIC='https://studio.milkcat.org/dashboard/agentos/one/v1/health'
LOCAL='http://127.0.0.1:8780/v1/health'

[ -d "$REPO/.git" ] || { echo "ERROR: repo missing" >&2; exit 2; }
[ -f "$DASH/package.json" ] || { echo "ERROR: dashboard missing" >&2; exit 2; }

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
  if [ -n "${PM2_ID:-}" ]; then
    pm2 restart "$PM2_ID" --update-env >/tmp/agentos-realm-gateway-rollback-pm2.log 2>&1
  fi
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

# Build the exact live dashboard after installing only the canonical gateway route.
(cd "$DASH" && npm run build)
echo "dashboard_build=PASS"

# Resolve exactly one PM2 process by its governed working directory; never accept a caller-supplied app name.
PM2_ID=$(pm2 jlist | python3 -c '
import json,sys
items=json.load(sys.stdin)
hits=[]
for item in items:
    env=item.get("pm2_env") or {}
    if env.get("pm_cwd") == "/home/ubuntu/agentmanager/dashboard":
        hits.append(str(env.get("pm_id", item.get("pm_id"))))
if len(hits) != 1:
    raise SystemExit("expected exactly one dashboard PM2 app, got %r" % hits)
print(hits[0])
')
echo "dashboard_pm2_id=$PM2_ID"
pm2 restart "$PM2_ID" --update-env

for i in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:3000/dashboard >/dev/null; then break; fi
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:3000/dashboard >/dev/null
echo "dashboard_local=PASS"

for i in $(seq 1 30); do
  BODY=$(curl -fsS --max-time 5 "$PUBLIC" 2>/dev/null || true)
  if printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1' && printf '%s' "$BODY" | grep -q 'realm-alston'; then break; fi
  sleep 1
done
BODY=$(curl -fsS --max-time 5 "$PUBLIC")
printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1'
printf '%s' "$BODY" | grep -q 'realm-alston'
echo "realm_gateway_public=PASS"
echo "realm_gateway_url=https://studio.milkcat.org/dashboard/agentos/one"
echo "nginx_mutation=NONE"
echo "root_privilege=NONE"
