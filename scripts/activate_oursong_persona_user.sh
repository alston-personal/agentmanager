#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 1001 ]]; then
  echo "oursong_activate=WRONG_USER"
  exit 2
fi

SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
REPO="${AGENTOS_REPO:-${HOME}/agentmanager}"
PROFILE_ROOT="${HOME}/.config/agentos/personas"
PROFILE="${PROFILE_ROOT}/oursong_alstonhuang.env"
RELEASE_ROOT="${HOME}/.local/share/agentos/persona-social/releases"

printf '%s' "${SOURCE_COMMIT}" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "oursong_activate=SOURCE_COMMIT_REQUIRED"
  exit 3
}
git -C "${REPO}" cat-file -e "${SOURCE_COMMIT}^{commit}"

mkdir -p "${RELEASE_ROOT}"
RELEASE="${RELEASE_ROOT}/${SOURCE_COMMIT}"
if [[ ! -d "${RELEASE}" ]]; then
  STAGE="${RELEASE_ROOT}/.stage-${SOURCE_COMMIT}-$$"
  rm -rf "${STAGE}"
  mkdir -p "${STAGE}"
  trap 'rm -rf "${STAGE:-}"' EXIT
  git -C "${REPO}" archive "${SOURCE_COMMIT}" | tar -x -C "${STAGE}"
  python3 -m py_compile     "${STAGE}/scripts/bootstrap_oursong_persona_user.py"     "${STAGE}/scripts/mio_persona_social_loop_user.py"     "${STAGE}/scripts/sync_persona_pdca_social_outcome_user.py"     "${STAGE}/agentos_node/persona_life.py"
  bash -n "${STAGE}/scripts/install_persona_social_timer_user.sh"
  mv "${STAGE}" "${RELEASE}"
  trap - EXIT
fi

test -f "${RELEASE}/scripts/bootstrap_oursong_persona_user.py"
test -f "${RELEASE}/scripts/mio_persona_social_loop_user.py"
test -f "${RELEASE}/scripts/sync_persona_pdca_social_outcome_user.py"
test -f "${RELEASE}/scripts/install_persona_social_timer_user.sh"

python3 "${RELEASE}/scripts/bootstrap_oursong_persona_user.py"

mkdir -p "${PROFILE_ROOT}"
chmod 700 "${PROFILE_ROOT}"

cat > "${PROFILE}" <<EOF
AGENTOS_PERSONA_SLUG=oursong_alstonhuang
AGENTOS_PERSONA_ID=oursong-alstonhuang-001
AGENTOS_PERSONA_DISPLAY=oursong_alstonhuang
AGENTOS_PERSONA_PROJECT_ID=oursong-alstonhuang-persona-social
AGENTOS_PERSONA_WRITE_PREFIX=oursong
AGENTOS_PERSONA_THREADS_HANDLES=oursong_alstonhuang
AGENTOS_PERSONA_SOCIAL_LOOP_SCRIPT=${RELEASE}/scripts/mio_persona_social_loop_user.py
AGENTOS_PERSONA_PDCA_SYNC_SCRIPT=${RELEASE}/scripts/sync_persona_pdca_social_outcome_user.py
EOF
chmod 600 "${PROFILE}"

bash "${RELEASE}/scripts/install_persona_social_timer_user.sh"
systemctl --user enable --now agentos-persona-social@oursong_alstonhuang.timer
systemctl --user start agentos-persona-social@oursong_alstonhuang.service

ln -sfn "${RELEASE}" "${HOME}/.local/share/agentos/persona-social/current-oursong_alstonhuang"

systemctl --user daemon-reload
systemctl --user enable --now agentos-persona-social@oursong_alstonhuang.timer

echo "oursong_source_commit=${SOURCE_COMMIT}"
echo "oursong_runtime_release=${RELEASE}"
echo "oursong_activate=PASS"
echo "oursong_timer=agentos-persona-social@oursong_alstonhuang.timer"
systemctl --user --no-pager --full status agentos-persona-social@oursong_alstonhuang.timer || true
