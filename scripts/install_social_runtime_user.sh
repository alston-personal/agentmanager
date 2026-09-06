#!/usr/bin/env bash
set -euo pipefail

EXPECTED_USER="agentos-node"
SOURCE_ROOT="${1:-$(pwd)}"
SOURCE_COMMIT="${2:-}"
RUNTIME_ROOT="${HOME}/.local/share/agentos/social-runtime"
STATE_ROOT="${HOME}/.local/state/agentos/social"
CONFIG_ROOT="${HOME}/.config/agentos"
UNIT_ROOT="${HOME}/.config/systemd/user"
ENV_FILE="${CONFIG_ROOT}/social-runtime.env"
UNIT_FILE="${UNIT_ROOT}/agentos-social-runtime.service"

if [ "$(id -un)" != "$EXPECTED_USER" ]; then
  echo "social_runtime_install=WRONG_USER"
  exit 2
fi
if ! printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "social_runtime_install=SOURCE_COMMIT_REQUIRED"
  exit 2
fi

test -f "$SOURCE_ROOT/agentos_node/social/runtime_http.py"
test -f "$SOURCE_ROOT/agentos_node/social/runtime_storage.py"

mkdir -p "$RUNTIME_ROOT/agentos_node" "$STATE_ROOT" "$CONFIG_ROOT" "$UNIT_ROOT"
rm -rf "$RUNTIME_ROOT/agentos_node/social"
cp -a "$SOURCE_ROOT/agentos_node/social" "$RUNTIME_ROOT/agentos_node/social"
cp "$SOURCE_ROOT/agentos_node/__init__.py" "$RUNTIME_ROOT/agentos_node/__init__.py"

cat > "$RUNTIME_ROOT/GENERATION" <<EOF
source_ref=core/integration
source_commit=$SOURCE_COMMIT
EOF
chmod -R go-rwx "$RUNTIME_ROOT" "$STATE_ROOT" || true

if [ ! -e "$ENV_FILE" ]; then
  umask 077
  cat > "$ENV_FILE" <<'EOF'
# Runtime-owned configuration. Do not commit values.
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
Description=AgentOS Shared Social Runtime
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

systemctl --user daemon-reload
systemctl --user enable --now agentos-social-runtime.service

for _ in $(seq 1 40); do
  if curl -fsS --max-time 2 http://127.0.0.1:8771/healthz >/tmp/agentos-social-runtime-health.json; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:8771/healthz >/tmp/agentos-social-runtime-health.json
python3 - <<'PY'
import json
p = json.load(open('/tmp/agentos-social-runtime-health.json', encoding='utf-8'))
assert p.get('schema') == 'agentos.social-runtime-status/v1', p
assert p.get('service') == 'agentos-social-runtime', p
threads = p.get('threads') or {}
assert isinstance(threads.get('configured'), bool), p
assert set(threads) == {'configured'}, p
print('social_runtime_health=PASS')
print('social_runtime_threads_configured=' + str(threads['configured']).lower())
PY

grep -q '^source_ref=core/integration$' "$RUNTIME_ROOT/GENERATION"
grep -q "^source_commit=$SOURCE_COMMIT$" "$RUNTIME_ROOT/GENERATION"
echo "social_runtime_source_ref=core/integration"
echo "social_runtime_source_commit=$SOURCE_COMMIT"
echo "social_runtime_install=PASS"
