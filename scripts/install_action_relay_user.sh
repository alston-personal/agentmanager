#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA="${AGENT_DATA_ROOT:-$HOME/agent-data}"
# Action Relay owns a dedicated runtime. Do not reuse action-runtime: that
# path is application/runtime asset space (for example character-blueprint).
RUNTIME_ROOT="${AGENTOS_ACTION_RUNTIME_ROOT:-$HOME/.local/share/agentos/action-relay-runtime}"
RELAY_ROOT="$DATA/runtime/action-relay"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-action-relay.service"
LEGACY_BACKUP=""

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$(dirname "$RUNTIME_ROOT")" "$UNIT_DIR"

if [ "${AGENTOS_ACTION_SPOOL_PREPROVISIONED:-0}" = 1 ]; then
  echo "action_relay_spool_preprovisioned=YES"
else
  mkdir -p "$RELAY_ROOT" "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts" "$RELAY_ROOT/quarantine"
  chgrp agentos "$RELAY_ROOT" "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts" "$RELAY_ROOT/quarantine"
  chmod 2770 "$RELAY_ROOT" "$RELAY_ROOT/inbox" "$RELAY_ROOT/processing" "$RELAY_ROOT/receipts" "$RELAY_ROOT/quarantine"
fi

git -C "$REPO" fetch origin main
if [ -e "$RUNTIME_ROOT/.git" ]; then
  git -C "$RUNTIME_ROOT" reset --hard origin/main
else
  if [ -e "$RUNTIME_ROOT" ] && [ -n "$(find "$RUNTIME_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    # Migrate only a narrowly-recognized Action Relay runtime shape and keep a
    # timestamped rollback snapshot. Unknown content is never removed.
    if [ ! -f "$RUNTIME_ROOT/agentos_node/action_relay.py" ]; then
      echo '=== UNKNOWN ACTION RELAY RUNTIME SHAPE (READ-ONLY) ===' >&2
      stat -c 'runtime_root=%n owner=%U:%G mode=%a type=%F' "$RUNTIME_ROOT" >&2 || true
      find "$RUNTIME_ROOT" -mindepth 1 -maxdepth 2 -printf 'runtime_entry=%y %P\n' 2>/dev/null | LC_ALL=C sort | head -n 120 >&2 || true
      for marker in \
        agentos_node/action_relay.py \
        current/agentos_node/action_relay.py \
        src/agentos_node/action_relay.py \
        runtime/agentos_node/action_relay.py \
        .git; do
        if [ -e "$RUNTIME_ROOT/$marker" ]; then
          echo "runtime_marker=$marker" >&2
        fi
      done
      echo "ERROR: non-empty runtime root is neither a worktree nor recognized Action Relay runtime: $RUNTIME_ROOT" >&2
      exit 2
    fi
    unexpected="$(find "$RUNTIME_ROOT" -mindepth 1 -maxdepth 1 ! -name agentos_node ! -name __pycache__ -print -quit 2>/dev/null || true)"
    if [ -n "$unexpected" ]; then
      echo "ERROR: refusing Action Relay runtime migration because unexpected entry exists: $unexpected" >&2
      exit 2
    fi
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"
    LEGACY_BACKUP="${RUNTIME_ROOT}.legacy-${stamp}"
    mv "$RUNTIME_ROOT" "$LEGACY_BACKUP"
    echo "action_runtime_legacy_backup=$LEGACY_BACKUP"
  else
    rmdir "$RUNTIME_ROOT" 2>/dev/null || true
  fi
  git -C "$REPO" worktree prune
  git -C "$REPO" worktree add --detach "$RUNTIME_ROOT" origin/main
fi

(
  cd "$RUNTIME_ROOT"
  PYTHONPATH="$RUNTIME_ROOT" python3 - <<'PY'
from agentos_node.action_relay import ACTIONS
print('action_runtime_import=ok')
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
Environment=XDG_RUNTIME_DIR=/run/user/1001
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus
UMask=0007
ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.action_relay --root $RELAY_ROOT'
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
  if [ -n "$LEGACY_BACKUP" ]; then
    echo "action_runtime_legacy_backup_preserved=$LEGACY_BACKUP" >&2
  fi
  echo 'action_relay_install=FAIL' >&2
  exit 4
fi

echo "action_relay_install=PASS"
echo "action_relay_group_context=agentos"
echo "action_relay_user_bus=ubuntu:/run/user/1001/bus"
echo "action_relay_stable_liveness=PASS"
if [ -n "$LEGACY_BACKUP" ]; then
  echo "action_runtime_migration=PASS"
  echo "action_runtime_legacy_backup=$LEGACY_BACKUP"
fi
echo "runtime=$RUNTIME_ROOT"
echo "spool=$RELAY_ROOT"
echo "unit=$UNIT"
