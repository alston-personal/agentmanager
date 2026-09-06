#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "social_runtime_deploy=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
RUNTIME_ROOT="${HOME}/.local/share/agentos/social-runtime"
STATE_ROOT="${HOME}/.local/state/agentos/social"
CONFIG_ROOT="${HOME}/.config/agentos"
UNIT_ROOT="${HOME}/.config/systemd/user"
ENV_FILE="${CONFIG_ROOT}/social-runtime.env"
UNIT_FILE="${UNIT_ROOT}/agentos-social-runtime.service"
DASH="$REPO/dashboard"
ROUTE_REL='dashboard/app/api/social/[...path]/route.ts'
ROUTE="$REPO/$ROUTE_REL"
PUBLIC_HEALTH='https://studio.milkcat.org/dashboard/api/social/healthz'
PUBLIC_INTERNAL='https://studio.milkcat.org/dashboard/api/social/internal/v1/social/acceptances'
LOCAL_GATEWAY='http://127.0.0.1:3000/dashboard/api/social/healthz'
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "social_runtime_deploy=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
}
test -d "$REPO/.git" || { echo "social_runtime_deploy=REPO_MISSING" >&2; exit 2; }
test -f "$DASH/package.json" || { echo "social_gateway_deploy=DASHBOARD_MISSING" >&2; exit 2; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT"
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
git -C "$REPO" archive "$SOURCE_COMMIT" agentos_node/social agentos_node/__init__.py | tar -x -C "$TMP_ROOT"
mkdir -p "$TMP_ROOT/route"
git -C "$REPO" show "$SOURCE_COMMIT:$ROUTE_REL" > "$TMP_ROOT/route/route.ts"
test -f "$TMP_ROOT/agentos_node/social/runtime_http.py"
test -f "$TMP_ROOT/agentos_node/social/runtime_storage.py"
python3 -m compileall -q "$TMP_ROOT/agentos_node/social"
python3 - "$TMP_ROOT/route/route.ts" <<'PY'
from pathlib import Path
import sys
s = Path(sys.argv[1]).read_text(encoding='utf-8')
required = [
    '127.0.0.1:8771',
    '/v1/social/connect',
    '/v1/social/publish',
    '/v1/social/oauth/threads/callback',
    '/dashboard/api/social/v1/social/oauth/threads/callback',
    'x-agentos-social-gateway',
]
missing = [x for x in required if x not in s]
assert not missing, missing
assert '/internal/v1/social/acceptances' not in s
assert 'x-agentos-control-token' not in s.lower()
print('social_gateway_route_guard=PASS')
PY

mkdir -p "$RUNTIME_ROOT/agentos_node" "$STATE_ROOT" "$CONFIG_ROOT" "$UNIT_ROOT"
rm -rf "$RUNTIME_ROOT/agentos_node/social"
cp -a "$TMP_ROOT/agentos_node/social" "$RUNTIME_ROOT/agentos_node/social"
cp "$TMP_ROOT/agentos_node/__init__.py" "$RUNTIME_ROOT/agentos_node/__init__.py"
cat > "$RUNTIME_ROOT/GENERATION" <<EOF
source_ref=core/integration
source_commit=$SOURCE_COMMIT
EOF
chmod -R go-rwx "$RUNTIME_ROOT" "$STATE_ROOT" || true

if [ ! -e "$ENV_FILE" ]; then
  umask 077
  cat > "$ENV_FILE" <<'EOF'
# Runtime-owned shared configuration. Provider values are never committed.
AGENTOS_SOCIAL_PRODUCTS_JSON={}
AGENTOS_SOCIAL_CONTROL_TOKEN=
AGENTOS_THREADS_APP_ID=
AGENTOS_THREADS_APP_SECRET=
AGENTOS_THREADS_REDIRECT_URI=
EOF
fi
chmod 0600 "$ENV_FILE"

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=AgentOS Shared Social Runtime (Core control-plane identity)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$RUNTIME_ROOT
Environment=PYTHONPATH=$RUNTIME_ROOT
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 -m agentos_node.social.runtime_http --host 127.0.0.1 --port 8771 --credential-path $STATE_ROOT/credentials.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$RUNTIME_ROOT $STATE_ROOT $CONFIG_ROOT

[Install]
WantedBy=default.target
EOF

# ubuntu is the existing persistent Core control-plane identity on Oracle.
# This action deliberately adds no sudo/root/UID-switch or linger authority.
systemctl --user daemon-reload
systemctl --user enable agentos-social-runtime.service >/dev/null
systemctl --user restart agentos-social-runtime.service

stable=0
for _ in $(seq 1 20); do
  if systemctl --user is-active --quiet agentos-social-runtime.service; then
    stable=$((stable + 1))
    [ "$stable" -ge 3 ] && break
  else
    stable=0
  fi
  sleep 1
done
if [ "$stable" -lt 3 ]; then
  systemctl --user --no-pager --full status agentos-social-runtime.service || true
  journalctl --user -u agentos-social-runtime.service -n 80 --no-pager >&2 || true
  echo "social_runtime_stable_liveness=FAIL" >&2
  exit 4
fi

HEALTH_FILE="$STATE_ROOT/health.json"
curl -fsS --max-time 3 http://127.0.0.1:8771/healthz > "$HEALTH_FILE"
python3 - "$HEALTH_FILE" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
assert p.get('schema') == 'agentos.social-runtime-status/v1', p
assert p.get('service') == 'agentos-social-runtime', p
threads = p.get('threads') or {}
assert set(threads) == {'configured'}, p
assert isinstance(threads.get('configured'), bool), p
text = json.dumps(p, sort_keys=True).lower()
for forbidden in ('app_secret', 'access_token', 'refresh_token', 'authorization_code'):
    assert forbidden not in text, text
print('social_runtime_health=PASS')
print('social_runtime_threads_configured=' + str(threads['configured']).lower())
PY

find_dashboard_runtime() {
  python3 - "$DASH" <<'PY'
from pathlib import Path
import os, sys
root = Path('/proc'); target = str(Path(sys.argv[1]).resolve()); rows = []
for entry in root.iterdir():
    if not entry.name.isdigit(): continue
    pid = int(entry.name)
    try:
        if entry.stat().st_uid != os.getuid(): continue
        cwd = str((entry/'cwd').resolve())
        raw = (entry/'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8','replace').strip()
        ppid = -1
        for line in (entry/'status').read_text().splitlines():
            if line.startswith('PPid:'):
                ppid = int(line.split()[1]); break
        pgid = os.getpgid(pid)
    except (OSError, PermissionError, ProcessLookupError):
        continue
    if cwd == target and (raw.startswith('npm start') or 'next start' in raw or raw.startswith('next-server')):
        rows.append((pid, ppid, pgid, raw))
for pid, ppid, pgid, raw in sorted(rows):
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
  old_npm=$(printf '%s\n' "$before" | awk -F '\t' '$4 ~ /^npm start/ {print $1}')
  [ "$(printf '%s\n' "$old_npm" | sed '/^$/d' | wc -l)" -eq 1 ] || {
    echo "ERROR: expected exactly one dashboard npm start, got: $old_npm" >&2; return 4;
  }
  groups=$(printf '%s\n' "$before" | awk -F '\t' '{print $3}' | sort -nu)
  own_pgid=$(ps -o pgid= -p $$ | tr -d ' ')
  for pgid in $groups; do
    [ "$pgid" != "$own_pgid" ] || { echo "ERROR: refusing own process group" >&2; return 4; }
    kill -TERM -- "-$pgid" 2>/dev/null || true
  done
  new_npm=''
  for _ in $(seq 1 30); do
    sleep 1
    new_npm=$(find_dashboard_npm_pid 2>/dev/null || true)
    [ -n "$new_npm" ] && [ "$new_npm" != "$old_npm" ] && break
  done
  [ -n "$new_npm" ] && [ "$new_npm" != "$old_npm" ] || {
    echo "ERROR: dashboard supervisor did not restart npm start" >&2; return 4;
  }
  echo "social_gateway_dashboard_old_pid=$old_npm"
  echo "social_gateway_dashboard_new_pid=$new_npm"
}

mkdir -p "$(dirname "$ROUTE")"
BACKUP="$TMP_ROOT/route.backup"
HAD_ROUTE=0
if [ -f "$ROUTE" ]; then cp "$ROUTE" "$BACKUP"; HAD_ROUTE=1; fi
rollback_gateway() {
  set +e
  if [ "$HAD_ROUTE" = 1 ]; then cp "$BACKUP" "$ROUTE"; else rm -f "$ROUTE"; fi
  (cd "$DASH" && npm run build >/tmp/agentos-social-gateway-rollback-build.log 2>&1)
  restart_dashboard >/tmp/agentos-social-gateway-rollback-restart.log 2>&1 || true
  set -e
}
trap 'rc=$?; if [ $rc -ne 0 ]; then rollback_gateway; fi; rm -rf "$TMP_ROOT"; exit $rc' EXIT
cp "$TMP_ROOT/route/route.ts" "$ROUTE"
chmod 0664 "$ROUTE" || true
(cd "$DASH" && npm run build)
echo "social_gateway_dashboard_build=PASS"
restart_dashboard

for _ in $(seq 1 30); do
  if curl -fsS --max-time 3 "$LOCAL_GATEWAY" > "$TMP_ROOT/local-gateway-health.json" 2>/dev/null; then break; fi
  sleep 1
done
curl -fsS --max-time 3 "$LOCAL_GATEWAY" > "$TMP_ROOT/local-gateway-health.json"
grep -q 'agentos.social-runtime-status/v1' "$TMP_ROOT/local-gateway-health.json"
echo "social_gateway_local=PASS"

INTERNAL_CODE=$(curl -sS -o "$TMP_ROOT/internal-block.json" -w '%{http_code}' --max-time 5 -X POST "$PUBLIC_INTERNAL" -H 'content-type: application/json' --data '{}')
[ "$INTERNAL_CODE" = 404 ]
grep -q 'Social gateway route not allowlisted' "$TMP_ROOT/internal-block.json"
echo "social_gateway_internal_control_public=BLOCKED"

for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 "$PUBLIC_HEALTH" > "$TMP_ROOT/public-health.json" 2>/dev/null; then break; fi
  sleep 1
done
curl -fsS --max-time 5 "$PUBLIC_HEALTH" > "$TMP_ROOT/public-health.json"
python3 - "$TMP_ROOT/public-health.json" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
assert p.get('schema') == 'agentos.social-runtime-status/v1', p
assert p.get('service') == 'agentos-social-runtime', p
assert set(p.get('threads') or {}) == {'configured'}, p
print('social_gateway_public=PASS')
print('social_gateway_public_configured=' + str(p['threads']['configured']).lower())
PY

grep -q '^source_ref=core/integration$' "$RUNTIME_ROOT/GENERATION"
grep -q "^source_commit=$SOURCE_COMMIT$" "$RUNTIME_ROOT/GENERATION"
echo "social_runtime_service_identity=ubuntu"
echo "social_runtime_root_privilege=NONE"
echo "social_runtime_source_ref=core/integration"
echo "social_runtime_source_commit=$SOURCE_COMMIT"
echo "social_runtime_stable_liveness=PASS"
echo "social_gateway_url=https://studio.milkcat.org/dashboard/api/social"
echo "social_gateway_nginx_mutation=NONE"
echo "social_runtime_deploy=PASS"
