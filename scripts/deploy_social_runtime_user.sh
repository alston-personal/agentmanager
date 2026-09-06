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
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "social_runtime_deploy=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
}
test -d "$REPO/.git" || { echo "social_runtime_deploy=REPO_MISSING" >&2; exit 2; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT"
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
git -C "$REPO" archive "$SOURCE_COMMIT" agentos_node/social agentos_node/__init__.py | tar -x -C "$TMP_ROOT"
test -f "$TMP_ROOT/agentos_node/social/runtime_http.py"
test -f "$TMP_ROOT/agentos_node/social/runtime_storage.py"
python3 -m compileall -q "$TMP_ROOT/agentos_node/social"

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

grep -q '^source_ref=core/integration$' "$RUNTIME_ROOT/GENERATION"
grep -q "^source_commit=$SOURCE_COMMIT$" "$RUNTIME_ROOT/GENERATION"
echo "social_runtime_service_identity=ubuntu"
echo "social_runtime_root_privilege=NONE"
echo "social_runtime_source_ref=core/integration"
echo "social_runtime_source_commit=$SOURCE_COMMIT"
echo "social_runtime_stable_liveness=PASS"
echo "social_runtime_deploy=PASS"
