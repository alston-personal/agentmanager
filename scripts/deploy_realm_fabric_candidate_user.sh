#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
ROOT="${AGENTOS_REALM_FABRIC_ROOT:-/home/ubuntu/.local/share/agentos/realm-fabric}"
SOURCE_ROOT="$ROOT/source-releases"
ACTION_RUNTIME="${AGENTOS_ACTION_RUNTIME_ROOT:-/home/ubuntu/.local/share/agentos/action-runtime}"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-realm-fabric.service"
RELEASE="$SOURCE_ROOT/$SOURCE_COMMIT"

[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'ERROR: AGENTOS_SOURCE_COMMIT must be exact lowercase 40-hex commit' >&2
  exit 2
}
[ -d "$REPO/.git" ] || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
echo 'realm_fabric_source_commit_verified=PASS'

mkdir -p "$SOURCE_ROOT" "$UNIT_DIR" "$DATA_ROOT/logs"
TMPDIR=$(mktemp -d "$SOURCE_ROOT/.candidate-$SOURCE_COMMIT.XXXXXX")
UNIT_BACKUP="$TMPDIR/agentos-realm-fabric.service.before"
HAD_UNIT=0
if [ -f "$UNIT" ]; then
  cp "$UNIT" "$UNIT_BACKUP"
  HAD_UNIT=1
fi

cleanup() {
  rm -rf "$TMPDIR"
}
rollback() {
  rc=$?
  set +e
  if [ "$rc" -ne 0 ]; then
    echo 'realm_fabric_candidate_rollback=STARTED' >&2
    if [ "$HAD_UNIT" = 1 ]; then
      cp "$UNIT_BACKUP" "$UNIT"
    else
      rm -f "$UNIT"
    fi
    systemctl --user daemon-reload
    systemctl --user restart agentos-realm-fabric.service || true
    echo 'realm_fabric_candidate_rollback=COMPLETED' >&2
  fi
  cleanup
  exit "$rc"
}
trap rollback EXIT

git -C "$REPO" archive "$SOURCE_COMMIT" agent_core | tar -x -C "$TMPDIR"
test -f "$TMPDIR/agent_core/realm_server.py"
echo 'realm_fabric_source_archive=PASS'
grep -Fq "if selection == 'active':" "$TMPDIR/agent_core/realm_server.py"
grep -Fq 'ONE_ACTIVE_CONTINUATION' "$TMPDIR/agent_core/realm_server.py"
echo 'realm_fabric_active_resolve_source_guard=PASS'
PYTHONPATH="$TMPDIR:$ACTION_RUNTIME" /usr/bin/python3 -m py_compile \
  "$TMPDIR/agent_core/realm_server.py" \
  "$TMPDIR/agent_core/active_continuation.py" \
  "$TMPDIR/agent_core/realm_cli.py"
echo 'realm_fabric_candidate_compile=PASS'
(
  cd /tmp
  PYTHONPATH="$TMPDIR:$ACTION_RUNTIME" /usr/bin/python3 - <<'PY'
from agent_core.realm_server import RealmHTTPServer
from agent_core.active_continuation import resolve_active_continuation
print("realm_fabric_candidate_import=PASS")
PY
)

if [ ! -d "$RELEASE/agent_core" ]; then
  mkdir -p "$RELEASE"
  mv "$TMPDIR/agent_core" "$RELEASE/agent_core"
fi
test -f "$RELEASE/agent_core/realm_server.py"
echo 'realm_fabric_versioned_release=PASS'

cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS ONE Realm Fabric (ubuntu Core identity, agentos boundary)
After=network.target

[Service]
Type=simple
WorkingDirectory=$RELEASE
Environment=PYTHONPATH=$RELEASE:$ACTION_RUNTIME
Environment=AGENT_DATA_ROOT=$DATA_ROOT
UMask=0007
ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agent_core.realm_cli serve --host 127.0.0.1 --port 8780'
Restart=always
RestartSec=3
PrivateTmp=true
StandardOutput=append:$DATA_ROOT/logs/realm-fabric.log
StandardError=append:$DATA_ROOT/logs/realm-fabric.log

[Install]
WantedBy=default.target
EOF
chmod 0644 "$UNIT"

systemctl --user daemon-reload
systemctl --user enable agentos-realm-fabric.service >/dev/null
systemctl --user restart agentos-realm-fabric.service
for i in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8780/v1/health >/dev/null; then
    break
  fi
  sleep 1
done
systemctl --user is-active --quiet agentos-realm-fabric.service
curl -fsS --max-time 3 http://127.0.0.1:8780/v1/health >/dev/null

# No credential is supplied: 401 proves the active-resolve route exists while
# preserving the Node-owned bearer boundary. A stale server would return 404.
PROBE_BODY="$TMPDIR/resolve-active-probe.json"
PROBE_CODE=$(curl -sS -o "$PROBE_BODY" -w '%{http_code}' --max-time 5 \
  -H 'Content-Type: application/json' \
  -d '{"selection":"active"}' \
  http://127.0.0.1:8780/v1/resolve)
test "$PROBE_CODE" = 401
! grep -q '"error": "not found"\|"error":"not found"' "$PROBE_BODY"

echo "realm_fabric_source_commit=$SOURCE_COMMIT"
echo "realm_fabric_source_release=$RELEASE"
echo 'realm_fabric_active_resolve_route=PASS'
echo 'realm_fabric_credential_exposed=false'
echo 'realm_fabric_candidate_deploy=PASS'
trap - EXIT
cleanup
