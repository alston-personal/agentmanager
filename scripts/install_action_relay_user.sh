#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA="${AGENT_DATA_ROOT:-$HOME/agent-data}"
RUNTIME_ROOT="${AGENTOS_ACTION_RUNTIME_ROOT:-$HOME/.local/share/agentos/action-runtime}"
LEGACY_RUNTIME_ROOT="${RUNTIME_ROOT}.legacy-pre-worktree"
RELAY_ROOT="$DATA/runtime/action-relay"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-action-relay.service"
SOURCE_REF="${AGENTOS_ACTION_SOURCE_REF:-main}"
EXPECTED_SOURCE_COMMIT="${AGENTOS_ACTION_SOURCE_COMMIT:-}"

case "$SOURCE_REF" in
  main|core/integration|feature/realm-node-fabric-readiness) ;;
  *) echo "ERROR: AGENTOS_ACTION_SOURCE_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac
if [ -n "$EXPECTED_SOURCE_COMMIT" ] && ! printf '%s' "$EXPECTED_SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "ERROR: AGENTOS_ACTION_SOURCE_COMMIT must be a lowercase 40-character git SHA" >&2
  exit 4
fi

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$(dirname "$RUNTIME_ROOT")" "$UNIT_DIR"

ensure_shared_dir() {
  local path="$1"
  mkdir -p "$path"
  local owner group mode
  owner=$(stat -c '%U' "$path")
  group=$(stat -c '%G' "$path")
  mode=$(stat -c '%a' "$path")

  if [ "$group" != agentos ]; then
    if [ "$owner" != ubuntu ]; then
      echo "ERROR: $path has group=$group owner=$owner; ubuntu cannot repair foreign-owned shared boundary" >&2
      exit 5
    fi
    chgrp agentos "$path"
    group=agentos
  fi

  if [ "$mode" != 2770 ]; then
    if [ "$owner" != ubuntu ]; then
      echo "ERROR: $path has mode=$mode owner=$owner; expected 2770 and ubuntu cannot chmod foreign-owned inode" >&2
      exit 5
    fi
    chmod 2770 "$path"
    mode=2770
  fi

  echo "action_relay_spool_dir=PASS path=$path owner=$owner group=$group mode=$mode"
}

if [ "${AGENTOS_ACTION_SPOOL_PREPROVISIONED:-0}" = 1 ]; then
  echo "action_relay_spool_preprovisioned=YES"
else
  ensure_shared_dir "$RELAY_ROOT"
  ensure_shared_dir "$RELAY_ROOT/inbox"
  ensure_shared_dir "$RELAY_ROOT/processing"
  ensure_shared_dir "$RELAY_ROOT/receipts"
  ensure_shared_dir "$RELAY_ROOT/quarantine"
fi

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
if [ -n "$EXPECTED_SOURCE_COMMIT" ] && [ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]; then
  echo "ERROR: Action Relay source generation mismatch: expected=$EXPECTED_SOURCE_COMMIT observed=$SOURCE_COMMIT" >&2
  exit 4
fi

# Historical Action Relay generations were materialized as a plain directory.
# Migrate that legitimate pre-worktree layout without deleting it. The migration
# is deliberately narrow: only an ubuntu-owned, non-symlink directory may move,
# and an existing deterministic backup makes the operation fail closed rather
# than overwriting prior evidence.
if [ -e "$RUNTIME_ROOT" ] && [ ! -e "$RUNTIME_ROOT/.git" ] && [ -n "$(find "$RUNTIME_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  test -d "$RUNTIME_ROOT" || { echo "ERROR: legacy runtime root is not a directory: $RUNTIME_ROOT" >&2; exit 2; }
  test ! -L "$RUNTIME_ROOT" || { echo "ERROR: legacy runtime root must not be a symlink: $RUNTIME_ROOT" >&2; exit 2; }
  owner=$(stat -c '%U' "$RUNTIME_ROOT")
  test "$owner" = ubuntu || { echo "ERROR: legacy runtime root must be ubuntu-owned: path=$RUNTIME_ROOT owner=$owner" >&2; exit 5; }
  test ! -e "$LEGACY_RUNTIME_ROOT" || { echo "ERROR: legacy runtime backup already exists: $LEGACY_RUNTIME_ROOT" >&2; exit 2; }
  mv "$RUNTIME_ROOT" "$LEGACY_RUNTIME_ROOT"
  echo "action_relay_legacy_runtime_migrated=PASS backup=$LEGACY_RUNTIME_ROOT"
fi

if [ -e "$RUNTIME_ROOT/.git" ]; then
  git -C "$RUNTIME_ROOT" reset --hard "$SOURCE_COMMIT"
else
  rmdir "$RUNTIME_ROOT" 2>/dev/null || true
  git -C "$REPO" worktree add --detach "$RUNTIME_ROOT" "$SOURCE_COMMIT"
fi

test "$(git -C "$RUNTIME_ROOT" rev-parse HEAD)" = "$SOURCE_COMMIT"
echo "action_relay_runtime_worktree=PASS"

(
  cd "$RUNTIME_ROOT"
  PYTHONPATH="$RUNTIME_ROOT" python3 - <<'PY'
from agentos_node.executor_job_action_relay import ACTION, ACTIONS
assert ACTION == 'agentos.executor.job'
assert ACTION in ACTIONS
print('action_runtime_import=ok')
print('executor_job_action_loaded=PASS')
print('actions='+','.join(sorted(ACTIONS)))
PY
)

cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Governed Action Relay (ubuntu identity, agentos boundary)
After=default.target

[Service]
Type=simple
WorkingDirectory=$RUNTIME_ROOT
Environment=PYTHONPATH=$RUNTIME_ROOT
Environment=AGENTOS_ACTION_RUNTIME_SOURCE_REF=$SOURCE_REF
Environment=AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT=$SOURCE_COMMIT
Environment=XDG_RUNTIME_DIR=/run/user/1001
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus
UMask=0007
ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.executor_job_action_relay --root $RELAY_ROOT'
Restart=on-failure
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-action-relay.service
systemctl --user restart agentos-action-relay.service

stable=0
for i in $(seq 1 20); do
  if systemctl --user is-active --quiet agentos-action-relay.service; then
    stable=$((stable + 1))
    if [ "$stable" -ge 3 ]; then break; fi
  else
    stable=0
  fi
  sleep 1
done

systemctl --user --no-pager --full status agentos-action-relay.service || true
if [ "$stable" -lt 3 ]; then
  echo '=== ACTION RELAY STARTUP JOURNAL ===' >&2
  journalctl --user -u agentos-action-relay.service -n 80 --no-pager >&2 || true
  echo 'action_relay_install=FAIL' >&2
  exit 4
fi

echo "action_relay_install=PASS"
echo "action_relay_executor_job_extension=PASS"
echo "action_relay_group_context=agentos"
echo "action_relay_user_bus=ubuntu:/run/user/1001/bus"
echo "action_relay_stable_liveness=PASS"
echo "action_relay_source_ref=$SOURCE_REF"
echo "action_relay_source_commit=$SOURCE_COMMIT"
echo "runtime=$RUNTIME_ROOT"
echo "spool=$RELAY_ROOT"
echo "unit=$UNIT"
