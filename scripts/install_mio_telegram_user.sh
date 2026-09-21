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
# Existing Mio persona is canonical in my-agent-data. Do not manufacture a
# second persona or overwrite an already present local, newer state.
DATA="$HOME/agent-data"
PERSONA="$DATA/personas/sunlake-milkcat"
if [ ! -f "$PERSONA/character_core.json" ] || [ ! -f "$PERSONA/persona_state.json" ] || [ ! -f "$PERSONA/reply_policy.json" ]; then
  if ! git -C "$DATA" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "mio_telegram_install=PERSONA_DATA_REPO_NOT_FOUND"
    exit 3
  fi
  origin="$(git -C "$DATA" remote get-url origin 2>/dev/null || true)"
  case "$origin" in
    git@github.com:alston-personal/my-agent-data|git@github.com:alston-personal/my-agent-data.git|https://github.com/alston-personal/my-agent-data|https://github.com/alston-personal/my-agent-data.git)
      ;;
    *)
      echo "mio_telegram_install=PERSONA_DATA_REMOTE_MISMATCH"
      exit 3
      ;;
  esac
  # Fetch only public-safe persona source, never credentials or secrets.
  git -C "$DATA" fetch --quiet --no-tags origin main || {
    echo "mio_telegram_install=PERSONA_DATA_FETCH_FAILED"
    exit 3
  }
  mkdir -p "$PERSONA"
  chmod 700 "$PERSONA"
  for filename in character_core.json persona_state.json reply_policy.json; do
    destination="$PERSONA/$filename"
    if [ ! -f "$destination" ]; then
      if git -C "$DATA" show "FETCH_HEAD:personas/sunlake-milkcat/$filename" > "$destination.tmp"; then
        chmod 600 "$destination.tmp"
        mv -n "$destination.tmp" "$destination"
        rm -f "$destination.tmp"
      else
        rm -f "$destination.tmp"
        echo "mio_telegram_install=PERSONA_SOURCE_MISSING"
        exit 3
      fi
    fi
  done
  # Existing public events may be consulted as evidence, but never overwrite
  # locally ingested events; private Telegram dialogue stays outside Git.
  mkdir -p "$PERSONA/events"
  if [ ! -e "$PERSONA/events/events.jsonl" ]; then
    if git -C "$DATA" cat-file -e "FETCH_HEAD:personas/sunlake-milkcat/events/events.jsonl" 2>/dev/null; then
      git -C "$DATA" show "FETCH_HEAD:personas/sunlake-milkcat/events/events.jsonl" > "$PERSONA/events/events.jsonl"
      chmod 600 "$PERSONA/events/events.jsonl"
    fi
  fi
  echo "mio_telegram_persona_source=MY_AGENT_DATA"
fi
test -f "$PERSONA/character_core.json"
test -f "$PERSONA/persona_state.json"
test -f "$PERSONA/reply_policy.json"
python3 - "$PERSONA" <<'PYCHECK'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
for name in ('character_core.json','persona_state.json','reply_policy.json'):
    obj=json.loads((root/name).read_text(encoding='utf-8'))
    if obj.get('character_id')!='sunlake-milkcat-ai-001':
        raise SystemExit('mio_telegram_install=PERSONA_ID_MISMATCH')
print('mio_telegram_persona_identity=PASS')
PYCHECK
chmod 600 "$ENV_FILE"
python3 -m py_compile "$PYTHON"
# Do not call getUpdates here: the already-running bot owns long polling.
(cd "$REPO" && PYTHONPATH="$REPO" /usr/bin/python3 -m scripts.mio_telegram_user verify)
# Never bind Telegram to the first untrusted inbound chat automatically.
if ! grep -Eq '^MIO_TELEGRAM_OWNER_ID=[1-9][0-9]*$' "$ENV_FILE"; then
  echo "mio_telegram_install=OWNER_PAIR_REQUIRED"
  (cd "$REPO" && PYTHONPATH="$REPO" /usr/bin/python3 -m scripts.mio_telegram_user pair)
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
ExecStart=/usr/bin/python3 -u -m scripts.mio_telegram_user run
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
