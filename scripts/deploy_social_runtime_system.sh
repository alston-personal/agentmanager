#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "social_runtime_deploy=WRONG_BOOTSTRAP_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
CANONICAL_REF="core/integration"
SERVICE_USER="agentos-node"
SERVICE_NAME="agentos-social-runtime.service"
RUNTIME_ROOT="/var/lib/agentos/social-runtime"
STATE_ROOT="/var/lib/agentos/social-runtime-state"
CONFIG_ROOT="/etc/agentos"
ENV_FILE="$CONFIG_ROOT/social-runtime.env"
UNIT_FILE="/etc/systemd/system/$SERVICE_NAME"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "social_runtime_deploy=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
}
test -d "$REPO/.git" || { echo "social_runtime_deploy=REPO_MISSING" >&2; exit 2; }
id "$SERVICE_USER" >/dev/null 2>&1 || { echo "social_runtime_deploy=SERVICE_USER_MISSING" >&2; exit 2; }

# Runtime-publishing bootstrap actions are fenced to the canonical integration
# generation. A request may carry an immutable SHA but cannot select a branch.
git -C "$REPO" fetch --no-tags origin "$CANONICAL_REF"
CANONICAL_HEAD="$(git -C "$REPO" rev-parse FETCH_HEAD)"
if [ "$CANONICAL_HEAD" != "$SOURCE_COMMIT" ]; then
  echo "social_runtime_deploy=NON_CANONICAL_SOURCE" >&2
  echo "social_runtime_source_ref=$CANONICAL_REF" >&2
  exit 3
fi
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
git -C "$REPO" archive "$SOURCE_COMMIT" agentos_node/social agentos_node/__init__.py | tar -x -C "$TMP_ROOT"
test -f "$TMP_ROOT/agentos_node/social/runtime_http.py"
test -f "$TMP_ROOT/agentos_node/social/runtime_storage.py"
python3 -m compileall -q "$TMP_ROOT/agentos_node/social"

cat > "$TMP_ROOT/social-runtime.env" <<'EOF'
# Host-local shared configuration. Provider credential values are never committed.
AGENTOS_SOCIAL_PRODUCTS_JSON={}
AGENTOS_SOCIAL_CONTROL_TOKEN=
AGENTOS_THREADS_APP_ID=
AGENTOS_THREADS_APP_SECRET=
AGENTOS_THREADS_REDIRECT_URI=
EOF
chmod 0600 "$TMP_ROOT/social-runtime.env"

cat > "$TMP_ROOT/$SERVICE_NAME" <<'EOF'
[Unit]
Description=AgentOS Shared Social Runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=agentos-node
WorkingDirectory=/var/lib/agentos/social-runtime
Environment=PYTHONPATH=/var/lib/agentos/social-runtime
EnvironmentFile=-/etc/agentos/social-runtime.env
ExecStart=/usr/bin/python3 -m agentos_node.social.runtime_http --host 127.0.0.1 --port 8771 --credential-path /var/lib/agentos/social-runtime-state/credentials.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/agentos/social-runtime-state

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$TMP_ROOT/$SERVICE_NAME"

# The bootstrap request cannot supply any sudo command, path, user, unit, or argv.
# Privileged effects below are a fixed implementation of the single allowlisted
# agentos.social_runtime.deploy action. No sudoers policy is created or widened.
sudo -n /usr/bin/install -d -m 0755 /var/lib/agentos
sudo -n /usr/bin/rm -rf "$RUNTIME_ROOT"
sudo -n /usr/bin/install -d -m 0755 "$RUNTIME_ROOT" "$CONFIG_ROOT"
sudo -n /usr/bin/install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$STATE_ROOT"
tar -C "$TMP_ROOT" -cf - agentos_node | sudo -n /usr/bin/tar -C "$RUNTIME_ROOT" -xf -

cat > "$TMP_ROOT/GENERATION" <<EOF
source_ref=$CANONICAL_REF
source_commit=$SOURCE_COMMIT
EOF
sudo -n /usr/bin/install -o root -g root -m 0644 "$TMP_ROOT/GENERATION" "$RUNTIME_ROOT/GENERATION"
sudo -n /usr/bin/chown -R root:root "$RUNTIME_ROOT/agentos_node"
sudo -n /usr/bin/chmod -R go-w "$RUNTIME_ROOT/agentos_node"

if ! sudo -n /usr/bin/test -e "$ENV_FILE"; then
  sudo -n /usr/bin/install -o root -g root -m 0600 "$TMP_ROOT/social-runtime.env" "$ENV_FILE"
fi
sudo -n /usr/bin/install -o root -g root -m 0644 "$TMP_ROOT/$SERVICE_NAME" "$UNIT_FILE"

sudo -n /usr/bin/systemctl daemon-reload
sudo -n /usr/bin/systemctl enable "$SERVICE_NAME" >/dev/null
sudo -n /usr/bin/systemctl restart "$SERVICE_NAME"

stable=0
for _ in $(seq 1 20); do
  if sudo -n /usr/bin/systemctl is-active --quiet "$SERVICE_NAME"; then
    stable=$((stable + 1))
    [ "$stable" -ge 3 ] && break
  else
    stable=0
  fi
  sleep 1
done
if [ "$stable" -lt 3 ]; then
  sudo -n /usr/bin/systemctl --no-pager --full status "$SERVICE_NAME" || true
  echo "social_runtime_stable_liveness=FAIL" >&2
  exit 4
fi

HEALTH_FILE="$TMP_ROOT/health.json"
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

grep -q '^source_ref=core/integration$' "$TMP_ROOT/GENERATION"
grep -q "^source_commit=$SOURCE_COMMIT$" "$TMP_ROOT/GENERATION"
echo "social_runtime_service_scope=system"
echo "social_runtime_service_identity=agentos-node"
echo "social_runtime_privileged_effect=FIXED_ACTION_ONLY"
echo "social_runtime_sudoers_mutation=NONE"
echo "social_runtime_source_ref=$CANONICAL_REF"
echo "social_runtime_source_commit=$SOURCE_COMMIT"
echo "social_runtime_stable_liveness=PASS"
echo "social_runtime_deploy=PASS"
