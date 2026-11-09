#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_observer_timer_install=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
if ! printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  echo "mio_observer_timer_install=SOURCE_COMMIT_REQUIRED" >&2
  exit 2
fi

BIN="$HOME/.local/bin"
UNIT="$HOME/.config/systemd/user"
mkdir -p "$BIN" "$UNIT"

RUNNER="$BIN/agentos-mio-observer-run"
cat > "$RUNNER" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
REPO=/home/ubuntu/agentmanager
git -C "$REPO" fetch origin core/integration >/dev/null 2>&1
SOURCE_COMMIT="$(git -C "$REPO" rev-parse origin/core/integration)"
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
TMP="$(mktemp)"
git -C "$REPO" show "$SOURCE_COMMIT:scripts/project_mio_observer_user.sh" > "$TMP"
chmod 0700 "$TMP"
AGENTOS_REPO="$REPO" AGENTOS_SOURCE_COMMIT="$SOURCE_COMMIT" bash "$TMP"
rm -f "$TMP"
SH
chmod 0755 "$RUNNER"

cat > "$UNIT/agentos-mio-observer.service" <<'UNIT'
[Unit]
Description=AgentOS Mio Observer Projection

[Service]
Type=oneshot
ExecStart=%h/.local/bin/agentos-mio-observer-run
UNIT

cat > "$UNIT/agentos-mio-observer.timer" <<'UNIT'
[Unit]
Description=Run Mio Observer every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=30s
Persistent=true
Unit=agentos-mio-observer.service

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now agentos-mio-observer.timer
systemctl --user start agentos-mio-observer.service

systemctl --user is-active --quiet agentos-mio-observer.timer
systemctl --user is-enabled --quiet agentos-mio-observer.timer
systemctl --user is-active --quiet agentos-mio-observer.service || true

test -s /home/ubuntu/zeus-writer/website/dist/personas/mio/activity.json

echo "mio_observer_timer=active"
echo "mio_observer_timer_interval=5m"
echo "mio_observer_timer_install=PASS"
