#!/usr/bin/env bash
# One-time ubuntu-owned setup. The legacy Telegram commander is not modified.
set -euo pipefail

if [ "$(id -un)" != ubuntu ]; then
  echo "mio_telegram_install=WRONG_USER"
  exit 2
fi
REPO="$(printenv AGENTOS_REPO || true)"
[ -n "$REPO" ] || REPO="$HOME/agentmanager"
ENV_FILE="$HOME/.config/agentos/mio-telegram.env"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/agentos-mio-telegram.service"
PYTHON="$REPO/scripts/mio_telegram_user.py"
test -f "$ENV_FILE" || { echo "mio_telegram_install=TOKEN_FILE_MISSING"; exit 3; }
test -f "$PYTHON" || { echo "mio_telegram_install=SOURCE_MISSING"; exit 3; }
test -f "$REPO/agentos_node/antigravity_relay.py" || { echo "mio_telegram_install=RELAY_CLIENT_MISSING"; exit 3; }
test -f "$HOME/agent-data/personas/sunlake-milkcat/character_core.json" || {
  echo "mio_telegram_install=PERSONA_DATA_MISSING"; exit 3;
}
chmod 600 "$ENV_FILE"
python3 -m py_compile "$PYTHON"
PYTHONPATH="$REPO" /usr/bin/python3 "$PYTHON" inspect
# Never bind Telegram to the first untrusted inbound chat automatically.
if ! grep -Eq '^MIO_TELEGRAM_OWNER_ID=[1-9][0-9]*$' "$ENV_FILE"; then
  echo "mio_telegram_install=OWNER_PAIR_REQUIRED"
  PYTHONPATH="$REPO" /usr/bin/python3 "$PYTHON" pair
fi
if ! systemctl --user is-active --quiet agentos-mio-agy-relay.service; then
  echo "mio_telegram_install=MIO_PERSONA_RELAY_NOT_ACTIVE"
  exit 5
fi

mkdir -p "$UNIT_DIR" "$HOME/agent-data/runtime/persona/sunlake-milkcat/telegram"
chmod 700 "$HOME/agent-data/runtime/persona/sunlake-milkcat/telegram"
cat > "$UNIT" <<EOF
[Unit]
Description=Mio owner-only Telegram Persona Bridge
After=network-online.target agentos-mio-agy-relay.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
Environment=AGENT_DATA_ROOT=$HOME/agent-data
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 -u $PYTHON run
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$HOME/agent-data/runtime/persona/sunlake-milkcat/telegram $HOME/agent-data/runtime/mio-antigravity-relay

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now agentos-mio-telegram.service >/dev/null
systemctl --user restart agentos-mio-telegram.service
sleep 2
if systemctl --user is-active --quiet agentos-mio-telegram.service; then
  echo "mio_telegram_install=PASS"
  echo "mio_telegram_service=ACTIVE"
else
  echo "mio_telegram_install=SERVICE_NOT_ACTIVE"
  exit 6
fi
