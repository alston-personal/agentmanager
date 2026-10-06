#!/usr/bin/env bash
set -euo pipefail

SOURCE_SHA="${1:?source sha required}"
RUN_ID="${2:?run id required}"
RUN_ATTEMPT="${3:?run attempt required}"

REPO=/home/ubuntu/agentmanager
RELEASE_ROOT=/home/ubuntu/agent-data/releases/dashboard-blue-green
RUNTIME_ROOT=/home/ubuntu/agent-data/runtime/dashboard
CONFIG=/home/ubuntu/.config/milkcat/dashboard.env.local
NGINX_SITE=/etc/nginx/sites-enabled/studio.milkcat.org

[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]
[[ "$RUN_ID" =~ ^[0-9]+$ ]]
[[ "$RUN_ATTEMPT" =~ ^[0-9]+$ ]]
test -d "$REPO/.git"
test -f "$CONFIG"
test -f "$NGINX_SITE"

exec 9>/tmp/agentos-dashboard-deploy.lock
flock -w 360 9
echo "dashboard_bg_lock=PASS"

ACTIVE_PORT="$(sed -n 's/.*set \$agentos_dashboard_upstream http:\/\/127\.0\.0\.1:\([0-9][0-9]*\);.*/\1/p' "$NGINX_SITE" | head -n1)"
case "$ACTIVE_PORT" in
  3040) TARGET_PORT=3041; TARGET_SLOT=green; OLD_UNIT=agentos-dashboard-blue.service ;;
  3041) TARGET_PORT=3040; TARGET_SLOT=blue; OLD_UNIT=agentos-dashboard-green.service ;;
  3000) TARGET_PORT=3040; TARGET_SLOT=blue; OLD_UNIT=agentos-dashboard.service ;;
  *) echo "ERROR: unsupported active Dashboard upstream: $ACTIVE_PORT" >&2; exit 3 ;;
esac
TARGET_LINK="$RUNTIME_ROOT/$TARGET_SLOT"
TARGET_UNIT="agentos-dashboard-$TARGET_SLOT.service"
RELEASE="$RELEASE_ROOT/$SOURCE_SHA-$RUN_ID-$RUN_ATTEMPT-$TARGET_SLOT"

echo "dashboard_bg_active_port=$ACTIVE_PORT"
echo "dashboard_bg_target_port=$TARGET_PORT"
echo "dashboard_bg_target_slot=$TARGET_SLOT"

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

MANIFEST=.next/server/app-paths-manifest.json
test -s "$MANIFEST"
node - <<'NODE'
const p=require('./.next/server/app-paths-manifest.json');
for (const r of [
  '/api/auth/session/route',
  '/api/auth/signin/[provider]/route',
  '/api/auth/callback/[provider]/route',
  '/api/agentos/[...path]/route',
  '/api/wardrobe/catalog/route',
  '/api/wardrobe/tryon/render/route',
  '/api/wardrobe/tryon/jobs/[jobId]/route',
  '/api/wardrobe/tryon/assets/[jobId]/route',
]) {
  if (!p[r]) throw new Error('missing built route: '+r);
}
console.log('dashboard_bg_built_routes=PASS');
NODE

ln -sfn "$RELEASE" "$RUNTIME_ROOT/.$TARGET_SLOT-candidate-$RUN_ID"
mv -Tf "$RUNTIME_ROOT/.$TARGET_SLOT-candidate-$RUN_ID" "$TARGET_LINK"

systemctl --user daemon-reload
systemctl --user restart "$TARGET_UNIT"

ready=0
for _ in $(seq 1 40); do
  s=$(curl -sS -o /tmp/bg-session -w '%{http_code}' --max-time 3 "http://127.0.0.1:$TARGET_PORT/dashboard/api/auth/session" || true)
  h=$(curl -sS -o /tmp/bg-health -w '%{http_code}' --max-time 3 "http://127.0.0.1:$TARGET_PORT/dashboard/api/agentos/v1/health" || true)
  c=$(curl -sS -o /tmp/bg-catalog -w '%{http_code}' --max-time 3 "http://127.0.0.1:$TARGET_PORT/dashboard/api/wardrobe/catalog?characterId=sunlake-milkcat-ai-001" || true)
  if [ "$s" = 200 ] && [ "$h" = 200 ] && [ "$c" = 200 ]; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
grep -q 'agentos.one-health/v0.1' /tmp/bg-health
echo "dashboard_bg_candidate_ready=PASS"

PID="$(ss -H -ltnp "sport = :$TARGET_PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)"
[[ "$PID" =~ ^[0-9]+$ ]]
CWD="$(readlink -f "/proc/$PID/cwd")"
test "$CWD" = "$RELEASE"
echo "dashboard_bg_candidate_identity=PASS"

sudo -n cp "$NGINX_SITE" "$NGINX_SITE.pre-bg-$RUN_ID-$RUN_ATTEMPT"
sudo -n python3 - "$NGINX_SITE" "$ACTIVE_PORT" "$TARGET_PORT" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); old=sys.argv[2]; new=sys.argv[3]
s=p.read_text()
a=f'set $agentos_dashboard_upstream http://127.0.0.1:{old};'
b=f'set $agentos_dashboard_upstream http://127.0.0.1:{new};'
if a not in s:
    raise SystemExit(f'active upstream marker missing: {a}')
p.write_text(s.replace(a,b,1))
PY

sudo -n nginx -t
sudo -n systemctl reload nginx
echo "dashboard_bg_nginx_switch=PASS"

public_ok=0
for _ in $(seq 1 20); do
  ps=$(curl -sS -o /tmp/bg-public-session -w '%{http_code}' --max-time 5 https://studio.milkcat.org/dashboard/api/auth/session || true)
  ph=$(curl -sS -o /tmp/bg-public-health -w '%{http_code}' --max-time 5 https://studio.milkcat.org/dashboard/api/agentos/v1/health || true)
  pc=$(curl -sS -o /tmp/bg-public-catalog -w '%{http_code}' --max-time 5 'https://studio.milkcat.org/dashboard/api/wardrobe/catalog?characterId=sunlake-milkcat-ai-001' || true)
  if [ "$ps" = 200 ] && [ "$ph" = 200 ] && [ "$pc" = 200 ]; then public_ok=1; break; fi
  sleep 0.5
done
if [ "$public_ok" != 1 ]; then
  sudo -n cp "$NGINX_SITE.pre-bg-$RUN_ID-$RUN_ATTEMPT" "$NGINX_SITE"
  sudo -n nginx -t
  sudo -n systemctl reload nginx
  echo "ERROR: public Dashboard verification failed; nginx upstream rolled back" >&2
  exit 8
fi
grep -q 'agentos.one-health/v0.1' /tmp/bg-public-health
echo "dashboard_bg_public_verify=PASS"

# Retire the previous slot only after the switched public surface has passed
# auth/session, Realm health, and application acceptance.
if systemctl --user is-active --quiet "$OLD_UNIT"; then
  systemctl --user stop "$OLD_UNIT"
fi
if systemctl --user is-active --quiet "$OLD_UNIT"; then
  echo "ERROR: old Dashboard slot is still active after retirement: $OLD_UNIT" >&2
  exit 9
fi
echo "dashboard_bg_old_slot_stopped=PASS"
echo "dashboard_bg_old_slot_unit=$OLD_UNIT"

# Prove the public surface remains healthy with only the new slot serving.
ps2=$(curl -sS -o /tmp/bg-public-session-post-retire -w '%{http_code}' --max-time 5 https://studio.milkcat.org/dashboard/api/auth/session || true)
ph2=$(curl -sS -o /tmp/bg-public-health-post-retire -w '%{http_code}' --max-time 5 https://studio.milkcat.org/dashboard/api/agentos/v1/health || true)
test "$ps2" = 200
test "$ph2" = 200
grep -q 'agentos.one-health/v0.1' /tmp/bg-public-health-post-retire
echo "dashboard_bg_post_retire_public_verify=PASS"

grep -Fq "set \$agentos_dashboard_upstream http://127.0.0.1:$TARGET_PORT;" "$NGINX_SITE"
printf 'source_sha=%s\nrun_id=%s\nrun_attempt=%s\nslot=%s\nport=%s\nstate=active\nrelease=%s\n'   "$SOURCE_SHA" "$RUN_ID" "$RUN_ATTEMPT" "$TARGET_SLOT" "$TARGET_PORT" "$RELEASE" > "$RELEASE/RELEASE_RECEIPT"

echo "$TARGET_SLOT" > /home/ubuntu/agent-data/runtime/dashboard-blue-green/active-slot
echo "$TARGET_PORT" > /home/ubuntu/agent-data/runtime/dashboard-blue-green/active-port
echo "dashboard_bg_cutover=PASS"
