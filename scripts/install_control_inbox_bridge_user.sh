#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
REALM_RUNTIME="${AGENTOS_REALM_RUNTIME:-/home/ubuntu/.local/share/agentos/realm-fabric/current}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
SOURCE_REF="${AGENTOS_REF:-feature/realm-node-fabric-readiness}"
CONTROL_REPOSITORY="${AGENTOS_CONTROL_REPOSITORY:-alston-personal/agentmanager}"
CONTROL_ISSUE="${AGENTOS_CONTROL_ISSUE:-50}"
ALLOWED_LOGIN="${AGENTOS_CONTROL_ALLOWED_LOGIN:-alstonhuang}"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
CONFIG_DIR="/home/ubuntu/.config/agentos"
CONTROLLER_ENV="$CONFIG_DIR/controller.env"
BRIDGE_ENV="$CONFIG_DIR/control-inbox.env"
BRIDGE_UNIT="$UNIT_DIR/agentos-control-inbox.service"
REALM_DROPIN_DIR="$UNIT_DIR/agentos-realm-fabric.service.d"
REALM_DROPIN="$REALM_DROPIN_DIR/controller.conf"
PROVENANCE="$DATA_ROOT/runtime/control-inbox/provenance.json"

case "$SOURCE_REF" in
  main|feature/realm-node-fabric-readiness) ;;
  *) echo "ERROR: AGENTOS_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac

case "$CONTROL_ISSUE" in
  ''|*[!0-9]*) echo "ERROR: AGENTOS_CONTROL_ISSUE must be numeric" >&2; exit 5 ;;
esac

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$REALM_RUNTIME/agent_core" "$UNIT_DIR" "$CONFIG_DIR" "$REALM_DROPIN_DIR" "$(dirname "$PROVENANCE")"
chmod 0700 "$CONFIG_DIR"

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
show_source() {
  git -C "$REPO" show "$SOURCE_COMMIT:$1"
}

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
for path in \
  agent_core/__init__.py \
  agent_core/node_registry.py \
  agent_core/node_bootstrap.py \
  agent_core/realm_fabric.py \
  agent_core/controller_api.py \
  agent_core/realm_server.py \
  agent_core/realm_cli.py \
  agent_core/control_inbox_bridge.py; do
  show_source "$path" > "$TMPDIR/$(basename "$path")"
done

install -m 0664 "$TMPDIR/__init__.py" "$REALM_RUNTIME/agent_core/__init__.py"
install -m 0664 "$TMPDIR/node_registry.py" "$REALM_RUNTIME/agent_core/node_registry.py"
install -m 0664 "$TMPDIR/node_bootstrap.py" "$REALM_RUNTIME/agent_core/node_bootstrap.py"
install -m 0664 "$TMPDIR/realm_fabric.py" "$REALM_RUNTIME/agent_core/realm_fabric.py"
install -m 0664 "$TMPDIR/controller_api.py" "$REALM_RUNTIME/agent_core/controller_api.py"
install -m 0664 "$TMPDIR/realm_server.py" "$REALM_RUNTIME/agent_core/realm_server.py"
install -m 0664 "$TMPDIR/realm_cli.py" "$REALM_RUNTIME/agent_core/realm_cli.py"
install -m 0664 "$TMPDIR/control_inbox_bridge.py" "$REALM_RUNTIME/agent_core/control_inbox_bridge.py"

if [ -f "$CONTROLLER_ENV" ]; then
  CONTROLLER_TOKEN=$(sed -n 's/^AGENTOS_CONTROLLER_TOKEN=//p' "$CONTROLLER_ENV" | head -n 1)
else
  CONTROLLER_TOKEN=''
fi
if [ -z "$CONTROLLER_TOKEN" ]; then
  CONTROLLER_TOKEN=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)
  umask 077
  printf 'AGENTOS_CONTROLLER_TOKEN=%s\n' "$CONTROLLER_TOKEN" > "$CONTROLLER_ENV"
fi
chmod 0600 "$CONTROLLER_ENV"

GITHUB_TOKEN="${AGENTOS_GITHUB_TOKEN:-${GH_TOKEN:-}}"
if [ -z "$GITHUB_TOKEN" ] && command -v gh >/dev/null 2>&1; then
  GITHUB_TOKEN=$(gh auth token 2>/dev/null || true)
fi
if [ -z "$GITHUB_TOKEN" ]; then
  CREDENTIAL=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null || true)
  GITHUB_TOKEN=$(printf '%s\n' "$CREDENTIAL" | sed -n 's/^password=//p' | head -n 1)
fi
if [ -z "$GITHUB_TOKEN" ]; then
  echo "ERROR: no GitHub write credential available for result comments" >&2
  echo "Provide AGENTOS_GITHUB_TOKEN once, or authenticate gh as ubuntu." >&2
  exit 20
fi

umask 077
cat > "$BRIDGE_ENV" <<EOF
AGENTOS_GITHUB_TOKEN=$GITHUB_TOKEN
AGENTOS_CONTROLLER_TOKEN=$CONTROLLER_TOKEN
AGENTOS_CONTROL_REPOSITORY=$CONTROL_REPOSITORY
AGENTOS_CONTROL_ISSUE=$CONTROL_ISSUE
AGENTOS_CONTROL_ALLOWED_LOGIN=$ALLOWED_LOGIN
AGENTOS_ONE_URL=http://127.0.0.1:8780
AGENTOS_CONTROL_POLL_SECONDS=3
AGENTOS_CONTROL_RECEIPT_WAIT_SECONDS=45
AGENT_DATA_ROOT=$DATA_ROOT
EOF
chmod 0600 "$BRIDGE_ENV"
unset GITHUB_TOKEN CREDENTIAL CONTROLLER_TOKEN

cat > "$REALM_DROPIN" <<EOF
[Service]
EnvironmentFile=$CONTROLLER_ENV
EOF
chmod 0644 "$REALM_DROPIN"

cat > "$BRIDGE_UNIT" <<EOF
[Unit]
Description=AgentOS GitHub Issue Bootstrap Control Inbox
After=network-online.target agentos-realm-fabric.service
Wants=network-online.target
Requires=agentos-realm-fabric.service

[Service]
Type=simple
WorkingDirectory=$REALM_RUNTIME
Environment=PYTHONPATH=$REALM_RUNTIME
EnvironmentFile=$BRIDGE_ENV
UMask=0077
ExecStart=/usr/bin/python3 -m agent_core.control_inbox_bridge
Restart=always
RestartSec=3
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA_ROOT/runtime/control-inbox

[Install]
WantedBy=default.target
EOF

mkdir -p "$DATA_ROOT/runtime/control-inbox"
chmod 0700 "$DATA_ROOT/runtime/control-inbox"

BRIDGE_SHA256=$(sha256sum "$REALM_RUNTIME/agent_core/control_inbox_bridge.py" | awk '{print $1}')
python3 - "$PROVENANCE" "$SOURCE_REF" "$SOURCE_COMMIT" "$BRIDGE_SHA256" "$CONTROL_REPOSITORY" "$CONTROL_ISSUE" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, source_ref, source_commit, bridge_sha, repository, issue = sys.argv[1:]
payload = {
    'schema': 'agentos.control-inbox-provenance/v0.1',
    'installed_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
    'source_ref': source_ref,
    'source_commit': source_commit,
    'bridge_sha256': bridge_sha,
    'repository': repository,
    'issue_number': int(issue),
}
Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
PY
chmod 0600 "$PROVENANCE"

systemctl --user daemon-reload
systemctl --user restart agentos-realm-fabric.service
systemctl --user enable agentos-realm-fabric.service >/dev/null
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:8780/v1/health >/dev/null; then break; fi
  sleep 1
done

CONTROLLER_TOKEN=$(sed -n 's/^AGENTOS_CONTROLLER_TOKEN=//p' "$CONTROLLER_ENV" | head -n 1)
CONTROLLER_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 \
  -H "Authorization: Bearer $CONTROLLER_TOKEN" \
  http://127.0.0.1:8780/v1/controller/realm)
unset CONTROLLER_TOKEN
test "$CONTROLLER_CODE" = 200 || { echo "ERROR: controller API validation returned HTTP $CONTROLLER_CODE" >&2; exit 21; }

systemctl --user restart agentos-control-inbox.service
systemctl --user enable agentos-control-inbox.service >/dev/null
sleep 1
systemctl --user is-active --quiet agentos-control-inbox.service

echo "control_inbox_install=PASS"
echo "agentos_source_ref=$SOURCE_REF"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "controller_api=PASS"
echo "controller_api_bind=127.0.0.1:8780"
echo "control_repository=$CONTROL_REPOSITORY"
echo "control_issue=$CONTROL_ISSUE"
echo "control_allowed_login=$ALLOWED_LOGIN"
echo "control_inbox_service=active"
echo "control_inbox_provenance=$PROVENANCE"
