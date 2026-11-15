#!/usr/bin/env bash
# Bounded, single-unit Oracle repair. Other Core units and core/current untouched.
set -euo pipefail
umask 077

SOURCE_SHA="${1:-}"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "teams_cutover=INVALID_SOURCE_SHA"; exit 2; }
test "$(id -un)" = ubuntu || { echo "teams_cutover=WRONG_OWNER"; exit 2; }

REPO=/home/ubuntu/agentmanager
DATA_ROOT=/home/ubuntu/agent-data
RELEASE_ROOT="$DATA_ROOT/releases/core"
RELEASE="$RELEASE_ROOT/$SOURCE_SHA"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/teams-commander.service"
SERVICE=teams-commander.service
ORIGINAL_WD="$REPO"

test -d "$REPO/.git" && test -f "$REPO/.env"
test -f "$UNIT" && test ! -L "$UNIT"
test "$(systemctl --user show "$SERVICE" -p FragmentPath --value)" = "$UNIT"
systemctl --user is-active --quiet "$SERVICE" || {
  echo "teams_cutover=NOT_PREVIOUSLY_ACTIVE"
  exit 3
}
pid_before="$(systemctl --user show "$SERVICE" -p MainPID --value)"
[[ "$pid_before" =~ ^[1-9][0-9]*$ ]]
working_before="$(systemctl --user show "$SERVICE" -p WorkingDirectory --value)"
cwd_before="$(readlink -f "/proc/$pid_before/cwd")"
[[ "$working_before" == "$ORIGINAL_WD" && "$cwd_before" == "$ORIGINAL_WD" ]] || {
  echo "teams_cutover=UNEXPECTED_EXISTING_OWNER"
  exit 3
}
# Fail closed on nonstandard units, override chains and absolute checkout scripts.
grep -Fxq "WorkingDirectory=$REPO" "$UNIT"
grep -Eq '^ExecStart=/[^[:space:]]+[[:space:]]+scripts/teams_bridge\.py[[:space:]]*$' "$UNIT" || {
  echo "teams_cutover=UNSUPPORTED_EXECSTART"
  exit 3
}
grep -q '^EnvironmentFile=' "$UNIT" || {
  echo "teams_cutover=MISSING_ENVIRONMENTFILE"
  exit 3
}
test -z "$(systemctl --user show "$SERVICE" -p DropInPaths --value)" || {
  echo "teams_cutover=UNEXPECTED_DROPINS"
  exit 3
}

# No systemd or service mutation before every exact-source preflight succeeds.
git -C "$REPO" fetch --no-tags origin "$SOURCE_SHA" >/dev/null
git -C "$REPO" cat-file -e "$SOURCE_SHA^{commit}"
mkdir -p "$RELEASE_ROOT"
if [ ! -e "$RELEASE/.git" ]; then
  test ! -e "$RELEASE" || {
    echo "teams_cutover=EXISTING_NON_WORKTREE_RELEASE"
    exit 4
  }
  git -C "$REPO" worktree add --detach "$RELEASE" "$SOURCE_SHA" >/dev/null
fi
test "$(git -C "$RELEASE" rev-parse HEAD)" = "$SOURCE_SHA"
test -f "$RELEASE/scripts/teams_bridge.py"
test -f "$RELEASE/scripts/service_utils.py"
test -f "$RELEASE/scripts/install_systemd_user.sh"
if [ ! -e "$RELEASE/.env" ]; then
  ln -s "$REPO/.env" "$RELEASE/.env"
fi
test -f "$RELEASE/.env"
# Execute a Python syntax check without importing runtime or exposing config.
python3 - "$RELEASE/scripts/teams_bridge.py" "$RELEASE/scripts/service_utils.py" <<'PY'
import ast, pathlib, sys
for name in sys.argv[1:]:
    ast.parse(pathlib.Path(name).read_text(encoding='utf-8'))
PY

BACKUP="$(mktemp -d /tmp/agentos-teams-immutable.XXXXXXXX)"
cp -a -- "$UNIT" "$BACKUP/teams-commander.service"
changed=0
finish() {
  rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ] && [ "$changed" = 1 ]; then
    echo "teams_cutover_rollback=BEGIN"
    cp -a -- "$BACKUP/teams-commander.service" "$UNIT" || true
    systemctl --user daemon-reload || true
    systemctl --user restart "$SERVICE" || true
    if systemctl --user is-active --quiet "$SERVICE"; then
      echo "teams_cutover_rollback=RESTARTED_PREVIOUS_OWNER"
    else
      echo "teams_cutover_rollback=FAILED"
    fi
  fi
  rm -rf -- "$BACKUP"
  exit "$rc"
}
trap finish EXIT

# Change only the single unit's WorkingDirectory; retain its previously
# accepted Python executable, EnvironmentFile, restart policy and port.
python3 - "$UNIT" "$ORIGINAL_WD" "$RELEASE" <<'PY'
from pathlib import Path
import os, sys, tempfile
unit = Path(sys.argv[1])
old = "WorkingDirectory=" + sys.argv[2]
new = "WorkingDirectory=" + sys.argv[3]
text = unit.read_text(encoding="utf-8")
assert text.count(old) == 1, "unexpected unit working-directory contract"
fd, path = tempfile.mkstemp(prefix="teams-commander.", dir=unit.parent)
try:
    os.fchmod(fd, unit.stat().st_mode & 0o777)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text.replace(old, new))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(path, unit)
finally:
    if os.path.exists(path):
        os.unlink(path)
PY
changed=1
systemctl --user daemon-reload
test "$(systemctl --user show "$SERVICE" -p WorkingDirectory --value)" = "$RELEASE"
systemctl --user restart "$SERVICE"
systemctl --user is-active --quiet "$SERVICE"

# Survive a meaningful restart interval, reject crash-loop false positives.
sleep 12
systemctl --user is-active --quiet "$SERVICE"
pid_after="$(systemctl --user show "$SERVICE" -p MainPID --value)"
[[ "$pid_after" =~ ^[1-9][0-9]*$ ]]
test "$pid_after" != "$pid_before"
cwd_after="$(readlink -f "/proc/$pid_after/cwd")"
test "$cwd_after" = "$RELEASE"
test "$(systemctl --user show "$SERVICE" -p WorkingDirectory --value)" = "$RELEASE"

# Health probe is localhost only, and outputs no endpoint/token/response body.
python3 - "$REPO/.env" <<'PY'
import json, pathlib, sys
from urllib.request import urlopen
port = 8776
p = pathlib.Path(sys.argv[1])
for raw in p.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == "TEAMS_BRIDGE_PORT":
        value = value.strip().strip('"').strip("'")
        if not value.isdigit() or not 1 <= int(value) <= 65535:
            raise SystemExit("teams_health=INVALID_PORT")
        port = int(value)
with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=4) as response:
    data = json.load(response)
assert data.get("ok") is True and data.get("service") == "agentos-teams-commander"
print("teams_health=PASS")
PY

echo "teams_cutover_source=$SOURCE_SHA"
echo "teams_cutover_unit=EXACT_IMMUTABLE_RELEASE"
echo "teams_cutover_pid_cwd=EXACT_IMMUTABLE_RELEASE"
echo "teams_cutover_other_core_units=UNTOUCHED"
echo "teams_cutover=PASS"
