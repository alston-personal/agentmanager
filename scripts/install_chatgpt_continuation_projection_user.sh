#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
REALM_RUNTIME="${AGENTOS_REALM_RUNTIME:-/home/ubuntu/.local/share/agentos/realm-fabric/current}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
SOURCE_REF="${AGENTOS_REF:-core/integration}"
EXPECTED_SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
CONFIG_DIR="/home/ubuntu/.config/agentos"
BRIDGE_ENV="$CONFIG_DIR/control-inbox.env"
UNIT_DIR="/home/ubuntu/.config/systemd/user"
SERVICE="$UNIT_DIR/agentos-chatgpt-continuation-projection.service"
TIMER="$UNIT_DIR/agentos-chatgpt-continuation-projection.timer"
PROVENANCE="$DATA_ROOT/runtime/control-inbox/chatgpt-continuation-projection-provenance.json"

case "$SOURCE_REF" in
  core/integration) ;;
  *) echo "ERROR: AGENTOS_REF is not allowlisted: $SOURCE_REF" >&2; exit 4 ;;
esac
if [ -z "$EXPECTED_SOURCE_COMMIT" ] || ! printf '%s' "$EXPECTED_SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "ERROR: AGENTOS_SOURCE_COMMIT must be an exact lowercase 40-hex commit SHA" >&2
  exit 6
fi

test -d "$REPO/.git" || { echo "ERROR: repo missing: $REPO" >&2; exit 2; }
test -f "$BRIDGE_ENV" || { echo "ERROR: Control Inbox environment missing: $BRIDGE_ENV" >&2; exit 20; }
mkdir -p "$REALM_RUNTIME/agent_core" "$UNIT_DIR" "$(dirname "$PROVENANCE")"

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
LANE_HEAD=$(git -C "$REPO" rev-parse FETCH_HEAD)
git -C "$REPO" fetch --no-tags origin "$EXPECTED_SOURCE_COMMIT"
SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
[ "$SOURCE_COMMIT" = "$EXPECTED_SOURCE_COMMIT" ] || { echo "ERROR: exact source fetch mismatch" >&2; exit 7; }
git -C "$REPO" merge-base --is-ancestor "$SOURCE_COMMIT" "$LANE_HEAD" || {
  echo "ERROR: source commit is not in governed core/integration lane" >&2
  exit 8
}

git -C "$REPO" show "$SOURCE_COMMIT:agent_core/chatgpt_continuation_projection.py" > "$REALM_RUNTIME/agent_core/chatgpt_continuation_projection.py"
chmod 0664 "$REALM_RUNTIME/agent_core/chatgpt_continuation_projection.py"
PYTHONPATH="$REALM_RUNTIME" python3 -m py_compile "$REALM_RUNTIME/agent_core/chatgpt_continuation_projection.py"

cat > "$SERVICE" <<EOF
[Unit]
Description=AgentOS private ChatGPT continuation projection
After=network-online.target agentos-realm-fabric.service agentos-control-inbox.service
Wants=network-online.target
Requires=agentos-realm-fabric.service

[Service]
Type=oneshot
WorkingDirectory=$REALM_RUNTIME
Environment=PYTHONPATH=$REALM_RUNTIME
EnvironmentFile=$BRIDGE_ENV
ExecStart=/usr/bin/python3 -m agent_core.chatgpt_continuation_projection
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
EOF
chmod 0644 "$SERVICE"

cat > "$TIMER" <<EOF
[Unit]
Description=Refresh private ChatGPT continuation projection

[Timer]
OnBootSec=15s
OnUnitActiveSec=60s
AccuracySec=5s
Unit=agentos-chatgpt-continuation-projection.service

[Install]
WantedBy=timers.target
EOF
chmod 0644 "$TIMER"

MODULE_SHA256=$(sha256sum "$REALM_RUNTIME/agent_core/chatgpt_continuation_projection.py" | awk '{print $1}')
python3 - "$PROVENANCE" "$SOURCE_REF" "$SOURCE_COMMIT" "$MODULE_SHA256" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, source_ref, source_commit, module_sha = sys.argv[1:]
payload = {
    "schema": "agentos.chatgpt-continuation-projection-provenance/v1",
    "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "source_ref": source_ref,
    "source_commit": source_commit,
    "module_sha256": module_sha,
    "one_authority": True,
    "private_carrier": "alston-personal/my-agent-data",
    "target_path": "projects/agentos-core/continuity/chatgpt-active.json",
    "credential_exposed": False,
}
Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
chmod 0600 "$PROVENANCE"

systemctl --user daemon-reload
systemctl --user enable agentos-chatgpt-continuation-projection.timer >/dev/null
# A synchronous first publication is the installation acceptance fence. If the
# private carrier cannot be updated, rollout fails rather than claiming hydration.
if ! systemctl --user start agentos-chatgpt-continuation-projection.service; then
  echo "chatgpt_continuation_projection_start=FAIL" >&2
  # The publisher emits only stable, secret-free error classifications. Surface
  # those journal lines through the bounded bootstrap receipt so rollout failures
  # are diagnosable without granting arbitrary shell or exposing credentials.
  journalctl --user -u agentos-chatgpt-continuation-projection.service \
    --since '2 minutes ago' --no-pager -o cat 2>/dev/null | tail -n 40 >&2 || true
  exit 21
fi
systemctl --user restart agentos-chatgpt-continuation-projection.timer
systemctl --user is-active --quiet agentos-chatgpt-continuation-projection.timer

echo "chatgpt_continuation_projection_install=PASS"
echo "chatgpt_continuation_projection_exact_generation=PASS"
echo "agentos_source_ref=$SOURCE_REF"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "chatgpt_continuation_projection_timer=active"
echo "chatgpt_continuation_projection_provenance=$PROVENANCE"
