#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 1001 ]]; then
  echo "oursong_activate=WRONG_USER"
  exit 2
fi

ROOT="${HOME}/agentmanager"
PROFILE_ROOT="${HOME}/.config/agentos/personas"
PROFILE="${PROFILE_ROOT}/oursong_alstonhuang.env"

cd "${ROOT}"

python3 scripts/bootstrap_oursong_persona_user.py
bash scripts/install_persona_social_timer_user.sh

mkdir -p "${PROFILE_ROOT}"
chmod 700 "${PROFILE_ROOT}"

cat > "${PROFILE}" <<'EOF'
AGENTOS_PERSONA_SLUG=oursong_alstonhuang
AGENTOS_PERSONA_ID=oursong-alstonhuang-001
AGENTOS_PERSONA_DISPLAY=oursong_alstonhuang
AGENTOS_PERSONA_PROJECT_ID=oursong-alstonhuang-persona-social
AGENTOS_PERSONA_WRITE_PREFIX=oursong
AGENTOS_PERSONA_THREADS_HANDLES=oursong_alstonhuang
EOF
chmod 600 "${PROFILE}"

systemctl --user daemon-reload
systemctl --user enable --now agentos-persona-social@oursong_alstonhuang.timer

echo "oursong_activate=PASS"
echo "oursong_timer=agentos-persona-social@oursong_alstonhuang.timer"
systemctl --user --no-pager --full status agentos-persona-social@oursong_alstonhuang.timer || true
