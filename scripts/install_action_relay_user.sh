#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
DATA="${AGENT_DATA_ROOT:-$HOME/agent-data}"
RUNTIME_ROOT="${AGENTOS_ACTION_RUNTIME_ROOT:-$HOME/.local/share/agentos/action-runtime}"
RELAY_ROOT="$DATA/runtime/action-relay"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-action-relay.service"

for user in ubuntu agentos-node; do
  id -Gn "$user" | tr ' ' '\n' | grep -qx agentos || { echo "ERROR: $user must belong to agentos group" >&2; exit 3; }
done

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
mkdir -p "$(dirname "$RUNTIME_ROOT")" "$UNIT_DIR"

# The Action Relay spool may be created by the agentos-node runner and therefore
# legitimately be owned by agentos-node:agentos. Membership in agentos grants
# ubuntu access, but Linux still forbids ubuntu from chgrp/chmod on another
# user's inode. Treat an already-correct shared boundary as immutable instead
# of trying to seize ownership. Only repair metadata when ubuntu owns the inode.
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

git -C "$REPO" fetch origin main
if [ -e "$RUNTIME_ROOT/.git" ]; then
  git -C "$RUNTIME_ROOT" reset --hard origin/main
else
  if [ -e "$RUNTIME_ROOT" ] && [ -n "$(find "$RUNTIME_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    echo "ERROR: non-empty runtime root is not a worktree: $RUNTIME_ROOT" >&2; exit 2
  fi
  rmdir "$RUNTIME_ROOT" 2>/dev/null || true
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
# Actions such as agentos.antigravity.restart and layoutlab.api.restart call
# systemctl --user from inside the relay worker. Pin them to ubuntu's existing
# user manager explicitly; the GitHub runner has a different session/bus.
Environment=XDG_RUNTIME_DIR=/run/user/1001
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus
UMask=0007
# sg is the deliberate supplementary-group bootstrap boundary for this old
# ubuntu user-manager session. NoNewPrivileges cannot be enabled here because
# it prevents the setgid helper from establishing the already-authorized
# agentos group context.
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

# Require stable liveness, not a transient active sample immediately before
# an auto-restart failure. The worker must remain active for three observations.
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
echo "action_relay_group_context=agentos"
echo "action_relay_user_bus=ubuntu:/run/user/1001/bus"
echo "action_relay_stable_liveness=PASS"
echo "runtime=$RUNTIME_ROOT"
echo "spool=$RELAY_ROOT"
echo "unit=$UNIT"
