#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "galaxy_monitor_runtime_migration=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
RUNTIME_BASE="$HOME/.local/share/agentos/galaxy-experiment-monitor"
RELEASE_ROOT="$RUNTIME_BASE/releases"
CURRENT="$RUNTIME_BASE/current"
UNIT_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
MONITOR_UNIT="$UNIT_ROOT/agentos-galaxy-experiment-monitor.service"
MIO_RELAY_UNIT="$UNIT_ROOT/agentos-mio-agy-relay.service"
MIO_RELAY_ROOT="$HOME/agent-data/runtime/mio-antigravity-relay"

printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$' || { echo 'galaxy_monitor_runtime_migration=SOURCE_COMMIT_REQUIRED' >&2; exit 2; }
test -d "$REPO/.git"
test -f "$MONITOR_UNIT"
test -f "$MIO_RELAY_UNIT"
git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT" >/dev/null
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
mkdir -p "$RELEASE_ROOT"
RELEASE="$RELEASE_ROOT/$SOURCE_COMMIT"
if [ ! -d "$RELEASE" ]; then
  TMP_RELEASE="$(mktemp -d "$RELEASE_ROOT/.tmp.XXXXXX")"
  trap 'rm -rf "$TMP_RELEASE"' EXIT
  git -C "$REPO" archive "$SOURCE_COMMIT" \
    agentos_node \
    scripts/monitor_galaxy_threads_experiment_user.py \
    scripts/monitor_social_post_experiment_user.py \
    scripts/run_social_post_experiment_queue_user.py \
    scripts/sync_sunlake_milkcat_persona_user.py \
    scripts/evolve_mio_persona_ir_user.py \
    scripts/mio_persona_social_loop_user.py \
    scripts/sync_mio_pdca_social_outcome_user.py \
    scripts/diagnose_mio_threads_search_scope_user.py \
    | tar -x -C "$TMP_RELEASE"
  python3 -m compileall -q "$TMP_RELEASE/agentos_node" "$TMP_RELEASE/scripts"
  printf 'source_ref=core/integration\nsource_commit=%s\n' "$SOURCE_COMMIT" > "$TMP_RELEASE/GENERATION"
  chmod -R go-w "$TMP_RELEASE"
  mv "$TMP_RELEASE" "$RELEASE"
  trap - EXIT
fi

python3 - "$MONITOR_UNIT" "$MIO_RELAY_UNIT" "$RELEASE" <<'PY'
from pathlib import Path
import os, re, sys, tempfile
release=sys.argv[3]
legacy='/home/ubuntu/agentmanager'
release_pattern=re.compile(r'/home/ubuntu/\.local/share/agentos/galaxy-experiment-monitor/releases/[0-9a-f]{40}')
for raw in sys.argv[1:3]:
    path=Path(raw)
    text=path.read_text(encoding='utf-8')
    known = legacy in text or release in text or bool(release_pattern.search(text))
    if not known:
        raise SystemExit(f'unit runtime root not recognized: {path.name}')
    text=text.replace(legacy, release)
    text=release_pattern.sub(release, text)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=str(path.parent),text=True)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as h:
            h.write(text); h.flush(); os.fsync(h.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
PY

systemctl --user daemon-reload
for unit in agentos-galaxy-experiment-monitor.service agentos-mio-agy-relay.service; do
  wd="$(systemctl --user show "$unit" -p WorkingDirectory --value)"
  test "$(readlink -f "$wd")" = "$RELEASE"
  systemctl --user cat "$unit" | grep -Fq "$RELEASE"
  ! systemctl --user cat "$unit" | grep -Fq '/home/ubuntu/agentmanager'
  echo "galaxy_monitor_unit_runtime=$unit:immutable"
done

relay_restart=NOT_ACTIVE
if systemctl --user is-active --quiet agentos-mio-agy-relay.service; then
  inbox_count="$(find "$MIO_RELAY_ROOT/inbox" -maxdepth 1 -type f -name 'relay-*.json' 2>/dev/null | wc -l)"
  processing_count="$(find "$MIO_RELAY_ROOT/processing" -maxdepth 1 -type f -name 'relay-*.json' 2>/dev/null | wc -l)"
  if [ "$inbox_count" -eq 0 ] && [ "$processing_count" -eq 0 ]; then
    systemctl --user restart agentos-mio-agy-relay.service
    systemctl --user is-active --quiet agentos-mio-agy-relay.service
    relay_restart=PASS_EMPTY_SPOOL
  else
    relay_restart=DEFERRED_NONEMPTY_SPOOL
  fi
fi

ln -sfn "$RELEASE" "$CURRENT"
test "$(readlink -f "$CURRENT")" = "$RELEASE"
echo "galaxy_monitor_runtime_source_commit=$SOURCE_COMMIT"
echo "galaxy_monitor_runtime_release=$RELEASE"
echo "galaxy_monitor_runtime_relay_restart=$relay_restart"
echo "galaxy_monitor_runtime_social_cycle_triggered=NO"
echo "galaxy_monitor_runtime_mutable_checkout_write=NONE"
echo "galaxy_monitor_runtime_migration=PASS"
