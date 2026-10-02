#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="${1:?source sha required}"
RUN_ID="${2:?run id required}"
REPO=/home/ubuntu/agentmanager
RELEASE_ROOT=/home/ubuntu/agent-data/releases/dashboard/apps
RUNTIME_ROOT=/home/ubuntu/agent-data/runtime/dashboard
LIVE="$RUNTIME_ROOT/current"
CONFIG_DIR=/home/ubuntu/.config/milkcat
CONFIG="$CONFIG_DIR/dashboard.env.local"
UNIT_DIR=/home/ubuntu/.config/systemd/user
UNIT="$UNIT_DIR/agentos-dashboard.service"
RELEASE="$RELEASE_ROOT/$SOURCE_SHA-$RUN_ID"
STAGE="$RELEASE"
PREV_LIVE="$(readlink -f "$LIVE" 2>/dev/null || true)"
SWITCHED=0

cleanup(){ :; }
rollback(){
  set +e
  if [ "$SWITCHED" = 1 ] && [ -n "$PREV_LIVE" ] && [ -d "$PREV_LIVE" ]; then
    ln -sfn "$PREV_LIVE" "$RUNTIME_ROOT/.rollback-$RUN_ID"
    mv -Tf "$RUNTIME_ROOT/.rollback-$RUN_ID" "$LIVE"
    systemctl --user restart agentos-dashboard.service
  fi
  set -e
}
finish(){
  rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ]; then rollback; fi
  cleanup
  exit "$rc"
}
trap finish EXIT

[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$RUN_ID" =~ ^[0-9]+$ ]]
test -d "$REPO/.git"

git -C "$REPO" fetch --no-tags origin "$SOURCE_SHA"
git -C "$REPO" cat-file -e "$SOURCE_SHA^{commit}"

mkdir -p "$RELEASE_ROOT" "$RUNTIME_ROOT" "$CONFIG_DIR" "$UNIT_DIR"
chmod 700 "$CONFIG_DIR"

if [ ! -f "$CONFIG" ]; then
  test -f "$REPO/dashboard/.env.local"
  cp "$REPO/dashboard/.env.local" "$CONFIG"
  chmod 600 "$CONFIG"
fi
test -f "$CONFIG"
test ! -L "$CONFIG"
chmod 600 "$CONFIG"

test ! -e "$RELEASE"
mkdir -p "$RELEASE"
git -C "$REPO" archive "$SOURCE_SHA:dashboard" | tar -x -C "$RELEASE"
cp "$CONFIG" "$RELEASE/.env.local"
chmod 600 "$RELEASE/.env.local"

cd "$RELEASE"
npm ci --ignore-scripts --no-audit --no-fund
npm run build

MANIFEST=.next/server/app-paths-manifest.json
test -s "$MANIFEST"
node - <<'NODE'
const p=require('./.next/server/app-paths-manifest.json');
for (const r of [
  '/api/auth/session/route',
  '/api/wardrobe/catalog/route',
  '/api/wardrobe/intake/route',
  '/api/wardrobe/auth-handoff/route',
  '/api/wardrobe/tryon/render/route',
  '/api/wardrobe/tryon/jobs/[jobId]/route',
  '/api/wardrobe/tryon/assets/[jobId]/route',
]) {
  if (!p[r]) throw new Error('missing built route: '+r);
}
console.log('mio_dashboard_built_routes=PASS');
NODE

if grep -RIl --binary-files=text '/tmp/mio-dashboard-release-' "$RELEASE/.next" > /tmp/mio-dashboard-stale-paths 2>/dev/null && [ -s /tmp/mio-dashboard-stale-paths ]; then
  echo "ERROR: stale temporary Next build path detected"
  cat /tmp/mio-dashboard-stale-paths
  exit 1
fi
echo "mio_dashboard_build_path=PASS"

cp "$CONFIG" "$RELEASE/.env.local"
chmod 600 "$RELEASE/.env.local"
printf 'source_sha=%s\nrun_id=%s\nstate=candidate\n' "$SOURCE_SHA" "$RUN_ID" > "$RELEASE/RELEASE_RECEIPT"

# Canary exact release before switching production.
(
  cd "$RELEASE"
  PORT=3099 ./node_modules/.bin/next start -H 127.0.0.1 > /tmp/mio-dashboard-canary-$RUN_ID.log 2>&1 &
  echo $! > /tmp/mio-dashboard-canary-$RUN_ID.pid
)
CANARY_PID="$(cat /tmp/mio-dashboard-canary-$RUN_ID.pid)"
canary_ok=0
for _ in $(seq 1 30); do
  code="$(curl -sS -o /tmp/mio-canary-body -w '%{http_code}' --max-time 4 http://127.0.0.1:3099/dashboard/api/wardrobe/catalog?characterId=sunlake-milkcat-ai-001 || true)"
  if [ "$code" = 200 ]; then canary_ok=1; break; fi
  sleep 1
done
kill "$CANARY_PID" 2>/dev/null || true
wait "$CANARY_PID" 2>/dev/null || true
test "$canary_ok" -eq 1
echo "mio_dashboard_canary=PASS"

# Serialize the production switch.
exec 9>/tmp/agentos-dashboard-deploy.lock
flock -w 180 9

ln -sfn "$RELEASE" "$RUNTIME_ROOT/.candidate-$RUN_ID"
mv -Tf "$RUNTIME_ROOT/.candidate-$RUN_ID" "$LIVE"
SWITCHED=1

cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Dashboard / Realm Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$LIVE
Environment=NODE_ENV=production
Environment=PORT=3000
EnvironmentFile=-$CONFIG
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5
KillMode=control-group
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable agentos-dashboard.service >/dev/null
systemctl --user restart agentos-dashboard.service

ready=0
for _ in $(seq 1 40); do
  code="$(curl -sS -o /tmp/mio-live-session -w '%{http_code}' --max-time 4 http://127.0.0.1:3000/dashboard/api/auth/session || true)"
  if [ "$code" = 200 ]; then ready=1; break; fi
  sleep 1
done
test "$ready" -eq 1

PID="$(ss -H -ltnp 'sport = :3000' 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
[[ "$PID" =~ ^[0-9]+$ ]]
CWD="$(readlink -f "/proc/$PID/cwd")"
test "$CWD" = "$RELEASE"
test "$(readlink -f "$LIVE")" = "$RELEASE"

for spec in   "/dashboard/api/wardrobe/catalog?characterId=sunlake-milkcat-ai-001:200"   "/dashboard/api/wardrobe/intake:401"
do
  route="${spec%:*}"; expected="${spec##*:}"
  code="$(curl -sS -o /tmp/mio-route-body -w '%{http_code}' --max-time 8 "http://127.0.0.1:3000$route")"
  echo "mio_dashboard_route=$route http=$code expected=$expected"
  test "$code" = "$expected"
done

code="$(curl -sS -o /tmp/mio-render-unauth -w '%{http_code}' --max-time 8 -X POST -H 'Content-Type: application/json' --data '{"characterId":"sunlake-milkcat-ai-001","selectedLayers":{"lower_main":"net-32235-711"}}' http://127.0.0.1:3000/dashboard/api/wardrobe/tryon/render)"
test "$code" = 401
echo "mio_dashboard_render_route=PASS"

code="$(curl -sS -o /tmp/mio-handoff -w '%{http_code}' --max-time 8 -X POST 'http://127.0.0.1:3000/dashboard/api/wardrobe/auth-handoff?action=start')"
test "$code" = 200
python3 - /tmp/mio-handoff <<'PY'
import json,sys
j=json.load(open(sys.argv[1],encoding='utf-8'))
assert j.get('handoffId') and j.get('signInUrl')
print('mio_dashboard_auth_handoff=PASS')
PY

printf 'source_sha=%s\nrun_id=%s\nstate=active\nrelease=%s\n' "$SOURCE_SHA" "$RUN_ID" "$RELEASE" > "$RELEASE/RELEASE_RECEIPT"
SWITCHED=0
echo "mio_dashboard_immutable_release=PASS"
