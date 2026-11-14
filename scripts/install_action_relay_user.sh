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
CAPABILITY_MARKER="$RELAY_ROOT/capabilities.json"
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


# The installer owns this transaction: a repair caller must not have to guess
# which unit, runtime generation or capability marker survived a partial update.
# Snapshot before the first worktree mutation; never overwrite a prior backup.
# Keep an exclusive installer lock and durable snapshot beside the runtime.
# A SIGKILL/power-loss cannot run EXIT traps: refuse any subsequent update
# rather than silently overwriting the interrupted transaction's evidence.
TXN_PARENT=$(dirname "$RUNTIME_ROOT")
TXN_LOCK="$TXN_PARENT/.action-relay-install.lock"
TXN_DIR="$TXN_PARENT/.action-relay-install.pending"
exec 9>"$TXN_LOCK"
if ! flock -n 9; then
  echo "ERROR: another Action Relay installer holds the transaction lock" >&2
  exit 71
fi
TXN_PENDING_AT_START=0
if [ -L "$TXN_DIR" ]; then
  echo "ERROR: symlink transaction state is forbidden" >&2
  exit 72
fi
if [ -e "$TXN_DIR" ]; then
  TXN_PENDING_AT_START=1
else
  # New installs fetch their governed source, but interrupted rollback must
  # work without network, GitHub access or new source-authority discovery.
  if [ -n "$EXPECTED_SOURCE_COMMIT" ]; then
    git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
    SOURCE_REF_HEAD=$(git -C "$REPO" rev-parse FETCH_HEAD)
    git -C "$REPO" fetch --no-tags origin "$EXPECTED_SOURCE_COMMIT"
    SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
    if [ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]; then
      echo "ERROR: Action Relay exact source fetch mismatch: expected=$EXPECTED_SOURCE_COMMIT observed=$SOURCE_COMMIT" >&2
      exit 4
    fi
    if ! git -C "$REPO" merge-base --is-ancestor "$SOURCE_COMMIT" "$SOURCE_REF_HEAD"; then
      echo "ERROR: Action Relay source commit is not in governed ref: ref=$SOURCE_REF ref_head=$SOURCE_REF_HEAD commit=$SOURCE_COMMIT" >&2
      exit 4
    fi
  else
    git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
    SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
  fi

  ( umask 077; mkdir "$TXN_DIR" )
fi
if [ "$TXN_PENDING_AT_START" = 0 ]; then
TXN_COMMITTED=0
TXN_UNIT_TOUCHED=0
TXN_RUNTIME_TOUCHED=0
TXN_RUNTIME_KIND=absent
TXN_OLD_HEAD=
TXN_UNIT_PRESENT=0
TXN_MARKER_PRESENT=0
TXN_OLD_ACTIVE=0
TXN_OLD_ENABLED=0

if [ -L "$UNIT" ] || [ -L "$CAPABILITY_MARKER" ] || [ -L "$RUNTIME_ROOT" ]; then
  echo "ERROR: transaction snapshot refuses symlink boundary" >&2
  rm -rf "$TXN_DIR"
  exit 70
fi
if [ -f "$UNIT" ]; then
  cp -p "$UNIT" "$TXN_DIR/unit"
  (cd "$TXN_DIR" && sha256sum unit > unit.sha256)
  sync -f "$TXN_DIR/unit"
  TXN_UNIT_PRESENT=1
fi
if [ -f "$CAPABILITY_MARKER" ]; then
  cp -p "$CAPABILITY_MARKER" "$TXN_DIR/capabilities"
  (cd "$TXN_DIR" && sha256sum capabilities > capabilities.sha256)
  sync -f "$TXN_DIR/capabilities"
  TXN_MARKER_PRESENT=1
fi
if systemctl --user is-active --quiet agentos-action-relay.service 2>/dev/null; then TXN_OLD_ACTIVE=1; fi
if systemctl --user is-enabled --quiet agentos-action-relay.service 2>/dev/null; then TXN_OLD_ENABLED=1; fi
if [ -e "$RUNTIME_ROOT/.git" ]; then
  TXN_RUNTIME_KIND=worktree
  TXN_OLD_HEAD=$(git -C "$RUNTIME_ROOT" rev-parse --verify HEAD)
  if [ -n "$(git -C "$RUNTIME_ROOT" status --porcelain)" ]; then
    echo "ERROR: transaction refuses dirty prior Action Relay worktree" >&2
    rm -rf "$TXN_DIR"
    exit 70
  fi
elif [ -d "$RUNTIME_ROOT" ]; then
  TXN_RUNTIME_KIND=directory
  # Only the existing narrowly governed legacy-directory migration may move this.
  if [ -e "$LEGACY_RUNTIME_ROOT" ]; then
    echo "ERROR: pre-existing legacy backup blocks transactional install" >&2
    rm -rf "$TXN_DIR"
    exit 70
  fi
elif [ -e "$RUNTIME_ROOT" ]; then
  echo "ERROR: transaction refuses unexpected runtime inode" >&2
  rm -rf "$TXN_DIR"
  exit 70
fi

fi

rollback_action_relay_install() {
  local original_status="$1" rollback_failed=0
  trap - EXIT
  if [ "$TXN_COMMITTED" = 1 ]; then
    rm -rf "$TXN_DIR"
    exit "$original_status"
  fi
  echo "action_relay_transaction=ROLLBACK_STARTED" >&2
  # Stop a possibly-new consumer before reverting its source or unit.
  if [ "$TXN_UNIT_TOUCHED" = 1 ] || [ "$TXN_RUNTIME_TOUCHED" = 1 ]; then
    if ! systemctl --user stop agentos-action-relay.service; then
      rm -f "$CAPABILITY_MARKER" || true
      echo "action_relay_transaction=ROLLBACK_FAILED reason=service_stop snapshot=$TXN_DIR" >&2
      exit 74
    fi
    if systemctl --user is-active --quiet agentos-action-relay.service; then
      rm -f "$CAPABILITY_MARKER" || true
      echo "action_relay_transaction=ROLLBACK_FAILED reason=service_remains_active snapshot=$TXN_DIR" >&2
      exit 74
    fi
  fi
  case "$TXN_RUNTIME_KIND" in
    worktree)
      git -C "$RUNTIME_ROOT" reset --hard "$TXN_OLD_HEAD" || rollback_failed=1
      ;;
    directory)
      if [ -e "$RUNTIME_ROOT/.git" ]; then
        git -C "$REPO" worktree remove --force "$RUNTIME_ROOT" || rollback_failed=1
      fi
      if [ -d "$LEGACY_RUNTIME_ROOT" ]; then
        mv "$LEGACY_RUNTIME_ROOT" "$RUNTIME_ROOT" || rollback_failed=1
      else
        # Missing the original directory backup is not a successful restore.
        # Keep the pending snapshot and invalidate the capability marker.
        rollback_failed=1
      fi
      ;;
    absent)
      if [ -e "$RUNTIME_ROOT/.git" ]; then
        git -C "$REPO" worktree remove --force "$RUNTIME_ROOT" || rollback_failed=1
      fi
      ;;
  esac
  if [ "$TXN_UNIT_PRESENT" = 1 ]; then
    cp -p "$TXN_DIR/unit" "$UNIT" || rollback_failed=1
  else
    rm -f "$UNIT" || rollback_failed=1
  fi
  if [ "$TXN_MARKER_PRESENT" = 1 ]; then
    cp -p "$TXN_DIR/capabilities" "$CAPABILITY_MARKER" || rollback_failed=1
  else
    rm -f "$CAPABILITY_MARKER" || rollback_failed=1
  fi
  if [ "$TXN_UNIT_TOUCHED" = 1 ] || [ "$TXN_RUNTIME_TOUCHED" = 1 ]; then
    systemctl --user daemon-reload || rollback_failed=1
    if [ "$TXN_OLD_ENABLED" = 1 ]; then
      systemctl --user enable agentos-action-relay.service || rollback_failed=1
    else
      systemctl --user disable agentos-action-relay.service || rollback_failed=1
    fi
    if [ "$TXN_OLD_ACTIVE" = 1 ]; then
      systemctl --user start agentos-action-relay.service || rollback_failed=1
      systemctl --user is-active --quiet agentos-action-relay.service || rollback_failed=1
    fi
  fi
  # A successful command is not proof that the prior generation is restored.
  # Verify bytes and state before deleting the only recovery snapshot.
  if [ "$TXN_RUNTIME_KIND" = worktree ]; then
    observed_head=$(git -C "$RUNTIME_ROOT" rev-parse HEAD 2>/dev/null) || rollback_failed=1
    if [ "$observed_head" != "$TXN_OLD_HEAD" ]; then rollback_failed=1; fi
  fi
  if [ "$TXN_UNIT_PRESENT" = 1 ]; then
    cmp -s "$TXN_DIR/unit" "$UNIT" || rollback_failed=1
  elif [ -e "$UNIT" ]; then
    rollback_failed=1
  fi
  if [ "$TXN_MARKER_PRESENT" = 1 ]; then
    cmp -s "$TXN_DIR/capabilities" "$CAPABILITY_MARKER" || rollback_failed=1
  elif [ -e "$CAPABILITY_MARKER" ]; then
    rollback_failed=1
  fi
  if [ "$TXN_OLD_ACTIVE" = 1 ]; then
    systemctl --user is-active --quiet agentos-action-relay.service || rollback_failed=1
  elif systemctl --user is-active --quiet agentos-action-relay.service; then
    rollback_failed=1
  fi
  if [ "$TXN_OLD_ENABLED" = 1 ]; then
    systemctl --user is-enabled --quiet agentos-action-relay.service || rollback_failed=1
  elif systemctl --user is-enabled --quiet agentos-action-relay.service; then
    rollback_failed=1
  fi
  if [ "$rollback_failed" = 0 ]; then
    echo "action_relay_transaction=ROLLED_BACK" >&2
    rm -rf "$TXN_DIR"
  else
    # Do not advertise an unverified runtime generation to ONE consumers.
    # Keep forensic snapshots, but invalidate the public capability marker.
    rm -f "$CAPABILITY_MARKER" || true
    echo "action_relay_transaction=ROLLBACK_FAILED snapshot=$TXN_DIR" >&2
    original_status=74
  fi
  if [ "$original_status" -eq 0 ]; then original_status=1; fi
  exit "$original_status"
}
# The only recovery route is this canonical installer, under the same
# exclusive lock. Never source a persisted file as shell code.
if [ "$TXN_PENDING_AT_START" = 1 ]; then
  test -d "$TXN_DIR" || { echo "ERROR: invalid pending transaction inode" >&2; exit 72; }
  test "$(stat -c '%U:%a' "$TXN_DIR")" = "ubuntu:700" || {
    echo "ERROR: pending transaction ownership/mode mismatch" >&2; exit 72;
  }
  test ! -L "$TXN_DIR/state" && test -f "$TXN_DIR/state" || {
    echo "ERROR: incomplete transaction snapshot; manual rescue required" >&2; exit 72;
  }
  state=$(cat "$TXN_DIR/state")
  # Fixed literal metadata, never evaluated. Reject additions and malformed SHAs.
  if ! [[ "$state" =~ ^prior_kind=(worktree|directory|absent)[[:space:]]prior_head=([0-9a-f]*)[[:space:]]unit_present=([01])[[:space:]]marker_present=([01])[[:space:]]was_active=([01])[[:space:]]was_enabled=([01])$ ]]; then
    echo "ERROR: invalid transaction metadata; manual rescue required" >&2; exit 72
  fi
  TXN_RUNTIME_KIND="${BASH_REMATCH[1]}"
  TXN_OLD_HEAD="${BASH_REMATCH[2]}"
  TXN_UNIT_PRESENT="${BASH_REMATCH[3]}"
  TXN_MARKER_PRESENT="${BASH_REMATCH[4]}"
  TXN_OLD_ACTIVE="${BASH_REMATCH[5]}"
  TXN_OLD_ENABLED="${BASH_REMATCH[6]}"
  if [ "$TXN_RUNTIME_KIND" = worktree ] && ! [[ "$TXN_OLD_HEAD" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ERROR: invalid previous worktree SHA" >&2; exit 72
  fi
  if [ "$TXN_RUNTIME_KIND" != worktree ] && [ -n "$TXN_OLD_HEAD" ]; then
    echo "ERROR: unexpected previous SHA" >&2; exit 72
  fi
  if [ "$TXN_UNIT_PRESENT" = 1 ]; then
    test ! -L "$TXN_DIR/unit" && test -f "$TXN_DIR/unit" || {
      echo "ERROR: missing unit backup; manual rescue required" >&2; exit 72;
    }
    if ! (cd "$TXN_DIR" && sha256sum -c unit.sha256 --status); then
      echo "ERROR: unit backup checksum mismatch; manual rescue required" >&2; exit 72
    fi
  fi
  if [ "$TXN_MARKER_PRESENT" = 1 ]; then
    test ! -L "$TXN_DIR/capabilities" && test -f "$TXN_DIR/capabilities" || {
      echo "ERROR: missing capability backup; manual rescue required" >&2; exit 72;
    }
    if ! (cd "$TXN_DIR" && sha256sum -c capabilities.sha256 --status); then
      echo "ERROR: capability backup checksum mismatch; manual rescue required" >&2; exit 72
    fi
  fi
  TXN_COMMITTED=0
  TXN_RUNTIME_TOUCHED=1
  TXN_UNIT_TOUCHED=1
  echo "action_relay_transaction=INTERRUPTED_RECOVERY_STARTED" >&2
  # A successful rollback exits 73 to force a fresh governed install and
  # exact-source revalidation, rather than falling through into an update.
  rollback_action_relay_install 73
fi

trap 'rollback_action_relay_install "$?"' EXIT
printf "prior_kind=%s prior_head=%s unit_present=%s marker_present=%s was_active=%s was_enabled=%s\n" \
  "$TXN_RUNTIME_KIND" "$TXN_OLD_HEAD" "$TXN_UNIT_PRESENT" "$TXN_MARKER_PRESENT" "$TXN_OLD_ACTIVE" "$TXN_OLD_ENABLED" > "$TXN_DIR/state"
sync -f "$TXN_DIR/state"
echo "action_relay_transaction=SNAPSHOT_READY"

# Converge to exactly one governed consumer for this spool.
# Never terminate a live consumer while a capsule may have unknown side effects.
# If the managed worker is already inactive, any leftover processing capsule is
# by definition interrupted. Reuse ActionRelayWorker's native at-most-once
# recovery: emit outcome=unknown, replayed=false, then quarantine.
if ! systemctl --user is-active --quiet agentos-action-relay.service 2>/dev/null && [ -e "$RUNTIME_ROOT/.git" ]; then
  PYTHONPATH="$RUNTIME_ROOT" /usr/bin/python3 - "$RELAY_ROOT" <<'PY'
from pathlib import Path
import sys
from agentos_node.action_relay import ActionRelayWorker

recovered = ActionRelayWorker(Path(sys.argv[1])).recover_interrupted()
print("action_relay_interrupted_recovered=" + str(len(recovered)))
PY
  echo "action_relay_offline_interrupted_recovery=PASS"
elif ! systemctl --user is-active --quiet agentos-action-relay.service 2>/dev/null; then
  if find "$RELAY_ROOT/processing" -maxdepth 1 -type f -name 'action-*.json' -print -quit | grep -q .; then
    echo "ERROR: interrupted processing exists without a canonical runtime to recover it" >&2
    exit 75
  fi
  echo "action_relay_offline_interrupted_recovery=NO_EXISTING_RUNTIME"
fi

# With a live managed worker, allow fresh processing to finish normally.
processing_clear=0
for i in $(seq 1 90); do
  if ! find "$RELAY_ROOT/processing" -maxdepth 1 -type f -name 'action-*.json' -print -quit | grep -q .; then
    processing_clear=1
    break
  fi
  sleep 1
done
if [ "$processing_clear" -ne 1 ]; then
  echo "ERROR: Action Relay processing did not drain before managed stop" >&2
  exit 62
fi
echo "action_relay_processing_drain=PASS"

TXN_UNIT_TOUCHED=1
if [ -f "$UNIT" ]; then
  if ! systemctl --user stop agentos-action-relay.service; then
    echo "ERROR: unable to stop managed Action Relay service" >&2
    exit 61
  fi
fi
if systemctl --user is-active --quiet agentos-action-relay.service 2>/dev/null; then
  echo "ERROR: managed Action Relay service remained active after stop" >&2
  exit 61
fi
echo "action_relay_managed_service_stopped=PASS"

# Close the drain/stop race fail-closed. Never clean up consumers if a capsule
# entered processing after the last pre-stop observation.
if find "$RELAY_ROOT/processing" -maxdepth 1 -type f -name 'action-*.json' -print -quit | grep -q .; then
  echo "ERROR: Action Relay processing appeared during drain/stop handoff" >&2
  exit 62
fi
echo "action_relay_processing_handoff=PASS"

relay_consumer_pids() {
  local pid comm cmdline
  while read -r pid; do
    [ -n "$pid" ] || continue
    state=$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null || true)
    [ "$state" = "Z" ] && continue
    comm=$(cat "/proc/$pid/comm" 2>/dev/null || true)
    case "$comm" in
      python|python3|python3.*) ;;
      *) continue ;;
    esac
    cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)
    case "$cmdline" in
      *"python3 -m agentos_node.action_relay --root $RELAY_ROOT"*|*"python3 -m agentos_node.executor_job_action_relay --root $RELAY_ROOT"*)
        printf '%s\n' "$pid"
        ;;
    esac
  done < <(
    pgrep -u "$(id -u)" -f "agentos_node\.(action_relay|executor_job_action_relay).*--root $RELAY_ROOT" || true
  )
}

mapfile -t stale_relay_pids < <(relay_consumer_pids)
for pid in "${stale_relay_pids[@]:-}"; do
  [ -n "$pid" ] || continue
  kill -TERM "$pid" 2>/dev/null || true
done

for i in $(seq 1 20); do
  mapfile -t remaining_relay_pids < <(relay_consumer_pids)
  if [ "${#remaining_relay_pids[@]}" -eq 0 ]; then
    break
  fi
  sleep 0.25
done
mapfile -t stubborn_relay_pids < <(relay_consumer_pids)
for pid in "${stubborn_relay_pids[@]:-}"; do
  [ -n "$pid" ] || continue
  kill -KILL "$pid" 2>/dev/null || true
done
for i in $(seq 1 20); do
  mapfile -t remaining_relay_pids < <(relay_consumer_pids)
  if [ "${#remaining_relay_pids[@]}" -eq 0 ]; then
    break
  fi
  sleep 0.25
done
mapfile -t remaining_relay_pids < <(relay_consumer_pids)
if [ "${#remaining_relay_pids[@]}" -ne 0 ]; then
  echo "ERROR: stale Action Relay consumer remains after bounded cleanup" >&2
  exit 63
fi
echo "action_relay_prior_consumers_cleared=PASS"

# Live consumer has now drained, stopped and been verified absent. Only now
# may the transaction replace the production worktree and import new actions.
# Historical Action Relay generations were materialized as a plain directory.
# Migrate that legitimate pre-worktree layout without deleting it. The migration
# is deliberately narrow: only an ubuntu-owned, non-symlink directory may move,
# and an existing deterministic backup makes the operation fail closed rather
# than overwriting prior evidence.
# Set before the first possible runtime mutation. EXIT rollback must stop the
# running consumer even if a reset/add/migration fails before the unit stop.
TXN_RUNTIME_TOUCHED=1
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
from agentos_node.runtime_converge_action_relay import ACTION as CONVERGE_ACTION
from agentos_node.content_publish_action_relay import ACTION as X_AUTH_ACTION
from agentos_node.content_publish_social_action_relay import BOOTSTRAP_ACTION, INSPECT_ACTION
assert ACTION == 'agentos.executor.job'
assert CONVERGE_ACTION == 'agentos.runtime.converge'
assert X_AUTH_ACTION == 'agentos.content.x.auth.inspect'
assert BOOTSTRAP_ACTION == 'agentos.content.social.bootstrap'
assert INSPECT_ACTION == 'agentos.content.social.inspect'
assert ACTION in ACTIONS
assert CONVERGE_ACTION in ACTIONS
assert X_AUTH_ACTION in ACTIONS
assert BOOTSTRAP_ACTION in ACTIONS
assert INSPECT_ACTION in ACTIONS
print('action_runtime_import=ok')
print('executor_job_action_loaded=PASS')
print('runtime_converge_action_loaded=PASS')
print('content_publish_x_auth_action_loaded=PASS')
print('content_publish_social_actions_loaded=PASS')
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
ExecStart=/usr/bin/sg agentos -c 'cd "$RUNTIME_ROOT" && exec /usr/bin/env PYTHONPATH="$RUNTIME_ROOT" AGENTOS_ACTION_RUNTIME_SOURCE_REF="$SOURCE_REF" AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT="$SOURCE_COMMIT" /usr/bin/python3 -m agentos_node.executor_job_action_relay --root "$RELAY_ROOT"'
Restart=on-failure
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable agentos-action-relay.service
systemctl --user start agentos-action-relay.service

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
  rm -f "$CAPABILITY_MARKER"
  echo '=== ACTION RELAY STARTUP JOURNAL ===' >&2
  journalctl --user -u agentos-action-relay.service -n 80 --no-pager >&2 || true
  if [ -d "$LEGACY_RUNTIME_ROOT" ]; then
    echo "action_runtime_legacy_backup_preserved=$LEGACY_RUNTIME_ROOT" >&2
  fi
  echo 'action_relay_install=FAIL' >&2
  exit 4
fi

mapfile -t live_relay_pids < <(relay_consumer_pids)
if [ "${#live_relay_pids[@]}" -ne 1 ]; then
  echo "ERROR: expected exactly one canonical Action Relay consumer; observed=${#live_relay_pids[@]}" >&2
  exit 64
fi
relay_pid="${live_relay_pids[0]}"
cmdline=$(tr '\0' ' ' < "/proc/$relay_pid/cmdline" 2>/dev/null || true)
case "$cmdline" in
  *"python3 -m agentos_node.executor_job_action_relay --root $RELAY_ROOT"*) ;;
  *) echo "ERROR: canonical Action Relay consumer command mismatch" >&2; exit 65 ;;
esac
# Do not inspect /proc/<pid>/environ here. The canonical worker is launched
# through sg(1), so the observed Python consumer may be a peer uid even though
# this installer owns the ubuntu user unit. hidepid/Yama configurations can
# legitimately deny cross-uid environ reads. Verify the exact generation at
# source-owned boundaries instead: the installed unit must pin both variables,
# its WorkingDirectory must be the immutable worktree, and that worktree HEAD
# must equal the requested exact commit.
unit_ref=$(systemctl --user show agentos-action-relay.service -p Environment --value)
case " $unit_ref " in
  *" AGENTOS_ACTION_RUNTIME_SOURCE_REF=$SOURCE_REF "*) ;;
  *) echo "ERROR: canonical Action Relay unit source-ref environment mismatch" >&2; exit 66 ;;
esac
case " $unit_ref " in
  *" AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT=$SOURCE_COMMIT "*) ;;
  *) echo "ERROR: canonical Action Relay unit source-commit environment mismatch" >&2; exit 67 ;;
esac
unit_cwd=$(systemctl --user show agentos-action-relay.service -p WorkingDirectory --value)
test "$(readlink -f "$unit_cwd")" = "$(readlink -f "$RUNTIME_ROOT")" || {
  echo "ERROR: canonical Action Relay working directory mismatch" >&2
  exit 68
}
test "$(git -C "$RUNTIME_ROOT" rev-parse HEAD)" = "$SOURCE_COMMIT" || {
  echo "ERROR: canonical Action Relay runtime HEAD mismatch" >&2
  exit 69
}
echo "action_relay_single_consumer=PASS"
echo "action_relay_runtime_generation_unit=PASS"
echo "action_relay_runtime_generation_env=PASS"

# Capability availability is installed-state evidence, not a source-code claim.
# Publish only after the exact immutable runtime imports both fixed semantic
# actions and the worker demonstrates stable liveness. Publication runs in the
# same fixed `agentos` effective-group boundary as the Action Relay worker; no
# caller-controlled shell, argv, path, or credential surface is introduced.
PUBLISHER="$RUNTIME_ROOT/scripts/publish_action_relay_capability.py"
test -f "$PUBLISHER" || { echo "ERROR: capability publisher missing from exact runtime" >&2; exit 4; }
grep -Fq 'capability_marker_payload' "$PUBLISHER" || { echo "ERROR: capability publisher is not bound to canonical capability_marker_payload" >&2; exit 4; }
/usr/bin/sg agentos -c "PYTHONPATH='$RUNTIME_ROOT' /usr/bin/python3 '$PUBLISHER' --marker '$CAPABILITY_MARKER' --source-ref '$SOURCE_REF' --source-commit '$SOURCE_COMMIT'"

TXN_COMMITTED=1
rm -rf "$TXN_DIR"
trap - EXIT
echo "action_relay_transaction=COMMITTED"
echo "action_relay_install=PASS"
echo "action_relay_executor_job_extension=PASS"
echo "action_relay_runtime_converge_extension=PASS"
echo "action_relay_content_publish_extension=PASS"
echo "action_relay_capability_marker=PASS"
echo "action_relay_capability_atomic_publish=PASS"
echo "action_relay_capability_group_context=PASS"
echo "action_relay_group_context=agentos"
echo "action_relay_user_bus=ubuntu:/run/user/1001/bus"
echo "action_relay_stable_liveness=PASS"
echo "action_relay_source_ref=$SOURCE_REF"
echo "action_relay_source_commit=$SOURCE_COMMIT"
echo "runtime=$RUNTIME_ROOT"
echo "spool=$RELAY_ROOT"
echo "unit=$UNIT"
