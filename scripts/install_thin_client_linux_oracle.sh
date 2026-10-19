#!/bin/bash
set -euo pipefail

REF="${1:-core/integration}"
ONE_URL="${AGENTOS_ONE_URL:-http://127.0.0.1:8780}"
NODE_ID="${AGENTOS_NODE_ID:-oracle-exec}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
ROOT="$HOME/.local/share/AgentOS"
STATE="$HOME/.agentos-oracle-exec"
WORKSPACE="$HOME/AgentOS"
LAUNCHER="$ROOT/agentos-client"
LOCK="$ROOT/install.lock"

command -v python3 >/dev/null || { echo "python3 is required"; exit 2; }
command -v git >/dev/null || { echo "git is required"; exit 2; }
command -v systemctl >/dev/null || { echo "systemctl is required"; exit 2; }
command -v flock >/dev/null || { echo "flock is required"; exit 2; }

mkdir -p "$ROOT" "$STATE" "$WORKSPACE"
exec 9>"$LOCK"
flock -n 9 || { echo "agentos_oracle_exec_install=ALREADY_RUNNING"; exit 0; }

# Retire stale pre-snapshot installers from the earlier pip-based generation.
pkill -f "$HOME/.local/share/AgentOS/venv/bin/python -m pip install -q --upgrade git+https://github.com/alston-personal/agentmanager.git@" 2>/dev/null || true

if [ -z "$SOURCE_COMMIT" ]; then
  SOURCE_COMMIT="$(git -C "$REPO" rev-parse "$REF")"
fi
[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid source commit" >&2; exit 2; }
if ! git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}" 2>/dev/null; then
  git -C "$REPO" fetch origin "$SOURCE_COMMIT"
fi
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"

RUNTIME="$ROOT/runtime/$SOURCE_COMMIT"
if [ ! -f "$RUNTIME/agentos_node/client_cli.py" ]; then
  TMP="$ROOT/runtime/.staging-$SOURCE_COMMIT-$"
  rm -rf "$TMP"
  mkdir -p "$TMP"
  git -C "$REPO" archive "$SOURCE_COMMIT" agentos_node agent_core | tar -x -C "$TMP"
  python3 -m py_compile "$TMP/agentos_node/client_cli.py" "$TMP/agentos_node/thin_client.py" "$TMP/agentos_node/thin_client_transport.py"
  mkdir -p "$ROOT/runtime"
  mv "$TMP" "$RUNTIME"
fi
# Runtime identity belongs to the immutable installed snapshot, not the current
# controller checkout or a stale launcher environment. ThinClient reads this
# adjacent to its loaded module and includes it in its manifest/heartbeat.
PROVENANCE="$RUNTIME/runtime-provenance.json"
if [ ! -f "$PROVENANCE" ]; then
  AGENTOS_PINNED_REF="$REF" AGENTOS_PINNED_SHA="$SOURCE_COMMIT" AGENTOS_PINNED_PATH="$PROVENANCE" python3 - <<'PY'
import json, os
from pathlib import Path
target = Path(os.environ["AGENTOS_PINNED_PATH"])
payload = {
    "schema": "agentos.thin-client-runtime/v0.1",
    "status": "observed",
    "source_ref": os.environ["AGENTOS_PINNED_REF"],
    "source_commit": os.environ["AGENTOS_PINNED_SHA"],
}
tmp = target.with_suffix(".json.tmp")
tmp.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
tmp.replace(target)
PY
fi
echo "agentos_oracle_exec_runtime_provenance=PASS"
ln -sfn "$RUNTIME" "$ROOT/current"

install_pinned_launcher() {
  cat > "$LAUNCHER" <<EOF
  #!/bin/bash
  export AGENTOS_CLIENT_HOME="$STATE"
  export PYTHONPATH="$ROOT/current"
  exec /usr/bin/python3 -m agentos_node.client_cli "\$@"
  EOF
  chmod 700 "$LAUNCHER"
}
install_pinned_launcher

if [ ! -f "$STATE/policy.json" ]; then
  cat > "$STATE/policy.json" <<EOF
{
  "schema": "agentos.client-policy/v0.1",
  "allowed_executables": ["git", "python3", "systemctl", "ss"],
  "readable_roots": ["$WORKSPACE"],
  "writable_roots": ["$WORKSPACE"],
  "employee_wake_root": null,
  "max_timeout_seconds": 120
}
EOF
  chmod 600 "$STATE/policy.json"
fi

if [ ! -f "$STATE/client.json" ]; then
  if curl -fsS --max-time 3 "$ONE_URL/v1/health" >/dev/null 2>&1; then
    INVITE_JSON="$(AGENT_DATA_ROOT=/home/ubuntu/agent-data PYTHONPATH="$ROOT/current" python3 -m agent_core.realm_cli invite --minutes 10 --label oracle-exec-bootstrap)"
    INVITE_ID="$(printf '%s' "$INVITE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["invite_id"])')"
    INVITE_CODE="$(printf '%s' "$INVITE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["code"])')"
    "$LAUNCHER" enroll --one "$ONE_URL" --invite-id "$INVITE_ID" --code "$INVITE_CODE" --node-id "$NODE_ID" >/dev/null
    unset INVITE_JSON INVITE_ID INVITE_CODE
    echo "agentos_oracle_exec_enrollment=LOCAL_INVITE_PASS"
  else
    echo "agentos_oracle_exec_install=ENROLLMENT_REQUIRED"
    echo "agentos_node_id=$NODE_ID"
    exec "$LAUNCHER" join --one "$ONE_URL" --node-id "$NODE_ID" --timeout-seconds 900
  fi
fi

PYTHONPATH="$ROOT/current" /usr/bin/python3 - <<'PY'
from agentos_node.onboarding import install_linux_node_supervisor
import json
r=install_linux_node_supervisor()
print(json.dumps(r, ensure_ascii=False))
if not r.get("supervisor_ready"):
    raise SystemExit(2)
PY
# Generic lifecycle installation re-materializes its launcher without the pinned
# Oracle snapshot PYTHONPATH. Restore the fixed launcher and restart the existing
# managed service, then require a fresh node-authored heartbeat.
install_pinned_launcher
systemctl --user restart agentos-thin-client.service
systemctl --user is-active --quiet agentos-thin-client.service
echo "agentos_oracle_exec_pinned_launcher_restored=PASS"
"$LAUNCHER" health
"$LAUNCHER" once
echo "agentos_oracle_exec_install=PASS"
echo "agentos_node_id=$NODE_ID"
