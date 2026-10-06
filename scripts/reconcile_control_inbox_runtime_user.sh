#!/usr/bin/env bash
set -euo pipefail

[ "$(id -un)" = "ubuntu" ] || { echo "ERROR: run as ubuntu" >&2; exit 2; }

SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
RUNTIME_BASE="${AGENTOS_CONTROL_INBOX_RUNTIME:-/home/ubuntu/.local/share/agentos/control-inbox}"
RELEASES="$RUNTIME_BASE/releases"
CURRENT="$RUNTIME_BASE/current"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/agentos-control-inbox.service"
ENV_FILE="${AGENTOS_CONTROL_ENV:-$HOME/.config/agentos/control-inbox.env}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"

[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "ERROR: exact AGENTOS_SOURCE_COMMIT required" >&2; exit 3; }
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"

mkdir -p "$RELEASES" "$UNIT_DIR" "$DATA_ROOT/runtime/control-inbox"
STAGE="$(mktemp -d "$RUNTIME_BASE/.stage-$SOURCE_COMMIT-XXXXXX")"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT
mkdir -p "$STAGE/agent_core" "$STAGE/scripts"

git -C "$REPO" show "$SOURCE_COMMIT:agent_core/__init__.py" > "$STAGE/agent_core/__init__.py"
git -C "$REPO" show "$SOURCE_COMMIT:agent_core/control_inbox_bridge.py" > "$STAGE/agent_core/control_inbox_bridge.py"
git -C "$REPO" show "$SOURCE_COMMIT:scripts/repair_control_inbox_github_auth_user.sh" > "$STAGE/scripts/repair_control_inbox_github_auth_user.sh"
chmod 0755 "$STAGE/scripts/repair_control_inbox_github_auth_user.sh"
PYTHONPATH="$STAGE" python3 -m py_compile "$STAGE/agent_core/control_inbox_bridge.py"
grep -Fq "'layoutlib_parity'" "$STAGE/agent_core/control_inbox_bridge.py"
grep -Fq "agentos.executor.job" "$STAGE/scripts/repair_control_inbox_github_auth_user.sh"

RELEASE="$RELEASES/$SOURCE_COMMIT"
if [ -d "$RELEASE" ]; then
  for rel in agent_core/__init__.py agent_core/control_inbox_bridge.py scripts/repair_control_inbox_github_auth_user.sh; do
    cmp -s "$STAGE/$rel" "$RELEASE/$rel" || {
      echo "ERROR: immutable Control Inbox release mismatch: $rel" >&2
      exit 4
    }
  done
  echo "control_inbox_release_existing=YES"
else
  chmod -R u=rwX,go=rX "$STAGE"
  mv "$STAGE" "$RELEASE"
  STAGE="$(mktemp -d "$RUNTIME_BASE/.cleanup-XXXXXX")"
  echo "control_inbox_release_created=YES"
fi

ln -sfn "$RELEASE" "$CURRENT.new"
mv -Tf "$CURRENT.new" "$CURRENT"

cat > "$UNIT.tmp" <<EOF
[Unit]
Description=AgentOS GitHub Issue Bootstrap Control Inbox
After=network-online.target agentos-realm-fabric.service
Wants=network-online.target
Requires=agentos-realm-fabric.service

[Service]
Type=simple
WorkingDirectory=$CURRENT
Environment=PYTHONPATH=$CURRENT
EnvironmentFile=$ENV_FILE
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
if [ ! -f "$UNIT" ] || ! cmp -s "$UNIT.tmp" "$UNIT"; then
  mv "$UNIT.tmp" "$UNIT"
  systemctl --user daemon-reload
  echo "control_inbox_unit_updated=YES"
else
  rm -f "$UNIT.tmp"
  echo "control_inbox_unit_updated=NO"
fi

AGENTOS_CONTROL_ENV="$ENV_FILE" AGENT_DATA_ROOT="$DATA_ROOT"   bash "$RELEASE/scripts/repair_control_inbox_github_auth_user.sh"

systemctl --user is-active --quiet agentos-control-inbox.service
[ "$(readlink -f "$CURRENT")" = "$RELEASE" ]
grep -Fq 'agentos.executor.job' "$ENV_FILE"
grep -Fq "WorkingDirectory=$CURRENT" "$UNIT"
grep -Fq "Environment=PYTHONPATH=$CURRENT" "$UNIT"

echo "control_inbox_source_commit=$SOURCE_COMMIT"
echo "control_inbox_runtime_release=$RELEASE"
echo "control_inbox_realm_restart=NO"
echo "control_inbox_safe_reconcile=PASS"
