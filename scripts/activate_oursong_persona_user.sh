#!/usr/bin/env bash
set -euo pipefail

CURRENT_STAGE="entry"
trap 'rc=$?; echo "oursong_activate_stage=${CURRENT_STAGE}_failed"; echo "oursong_activate=FAIL"; exit "$rc"' ERR

CURRENT_STAGE="identity_check"
echo "oursong_activate_stage=${CURRENT_STAGE}_start"
if [[ "$(id -u)" -ne 1001 ]]; then
  echo "oursong_activate=WRONG_USER"
  exit 2
fi

SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
REPO="${AGENTOS_REPO:-${HOME}/agentmanager}"
PROFILE_ROOT="${HOME}/.config/agentos/personas"
PROFILE="${PROFILE_ROOT}/oursong_alstonhuang.env"
RELEASE_ROOT="${HOME}/.local/share/agentos/persona-social/releases"

CURRENT_STAGE="source_commit_validate"
echo "oursong_activate_stage=${CURRENT_STAGE}_start"
printf '%s' "${SOURCE_COMMIT}" | grep -Eq '^[0-9a-f]{40}$' || {
  echo "oursong_activate=SOURCE_COMMIT_REQUIRED"
  exit 3
}
CURRENT_STAGE="source_commit_present"
echo "oursong_activate_stage=${CURRENT_STAGE}_start"
git -C "${REPO}" cat-file -e "${SOURCE_COMMIT}^{commit}"

CURRENT_STAGE="release_root_prepare"
echo "oursong_activate_stage=${CURRENT_STAGE}_start"
mkdir -p "${RELEASE_ROOT}"
RELEASE="${RELEASE_ROOT}/${SOURCE_COMMIT}"
if [[ ! -d "${RELEASE}" ]]; then
  CURRENT_STAGE="release_stage_prepare"
  echo "oursong_activate_stage=${CURRENT_STAGE}_start"
  STAGE="${RELEASE_ROOT}/.stage-${SOURCE_COMMIT}-$$"
  rm -rf "${STAGE}"
  mkdir -p "${STAGE}"
  trap 'rm -rf "${STAGE:-}"' EXIT
  CURRENT_STAGE="release_archive"
  echo "oursong_activate_stage=${CURRENT_STAGE}_start"
  git -C "${REPO}" archive "${SOURCE_COMMIT}" | tar -x -C "${STAGE}"
  CURRENT_STAGE="release_compile"
  echo "oursong_activate_stage=${CURRENT_STAGE}_start"
  python3 -m py_compile     "${STAGE}/scripts/bootstrap_oursong_persona_user.py"     "${STAGE}/scripts/mio_persona_social_loop_user.py"     "${STAGE}/scripts/sync_persona_pdca_social_outcome_user.py"     "${STAGE}/scripts/persona_pdca_heartbeat_user.py"     "${STAGE}/agentos_node/persona_life.py"
  CURRENT_STAGE="release_shellcheck"
  echo "oursong_activate_stage=${CURRENT_STAGE}_start"
  bash -n "${STAGE}/scripts/install_persona_social_timer_user.sh"
  CURRENT_STAGE="release_publish"
  echo "oursong_activate_stage=${CURRENT_STAGE}_start"
  mv "${STAGE}" "${RELEASE}"
  trap - EXIT
fi

test -f "${RELEASE}/scripts/bootstrap_oursong_persona_user.py"
test -f "${RELEASE}/scripts/mio_persona_social_loop_user.py"
test -f "${RELEASE}/scripts/sync_persona_pdca_social_outcome_user.py"
test -f "${RELEASE}/scripts/install_persona_social_timer_user.sh"
test -f "${RELEASE}/scripts/persona_pdca_heartbeat_user.py"

CURRENT_STAGE="bootstrap"
echo "oursong_activate_stage=bootstrap_start"
python3 "${RELEASE}/scripts/bootstrap_oursong_persona_user.py"
echo "oursong_activate_stage=bootstrap_pass"

# Cut over the legacy runtime-only producer to the repo-owned generic producer.
# Keep the existing systemd unit/timer contract so rollback is a single symlink/file restore.
echo "oursong_activate_stage=heartbeat_install_start"
install -m 0755 "${RELEASE}/scripts/persona_pdca_heartbeat_user.py" "${HOME}/.local/bin/agentos-persona-pdca-heartbeat"
echo "oursong_activate_stage=heartbeat_install_pass"
systemctl --user daemon-reload
echo "oursong_activate_stage=heartbeat_start"
if ! systemctl --user start agentos-persona-pdca-heartbeat.service; then
  echo "oursong_activate_stage=heartbeat_failed"
  systemctl --user --no-pager --full status agentos-persona-pdca-heartbeat.service || true
  journalctl --user -u agentos-persona-pdca-heartbeat.service -n 20 --no-pager || true
  HB_CLASS="$(journalctl --user -u agentos-persona-pdca-heartbeat.service -n 50 --no-pager -o cat 2>/dev/null | grep -Eo 'persona_pdca_heartbeat=[A-Z_]+' | tail -n 1 || true)"
  if [[ -n "$HB_CLASS" ]]; then
    echo "$HB_CLASS"
  else
    echo "persona_pdca_heartbeat=UNKNOWN_FAILURE"
  fi
  exit 11
fi
echo "oursong_activate_stage=heartbeat_pass"
HB_RECEIPT="${HOME}/.local/share/agentos/runtime/persona-pdca/heartbeat-receipt.json"
python3 - "${HB_RECEIPT}" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
payload=json.loads(p.read_text(encoding="utf-8"))
assert payload.get("schema")=="agentos.persona-pdca-heartbeat-receipt/v1", payload
assert payload.get("status")=="PASS", payload
matches=[x for x in payload.get("personas") or [] if x.get("slug")=="oursong_alstonhuang"]
assert len(matches)==1, payload
row=matches[0]
assert int(row.get("cycle") or 0)>=1, row
assert payload.get("observed_at"), payload
print("oursong_heartbeat_cutover=PASS")
print("oursong_heartbeat_cycle="+str(row["cycle"]))
print("oursong_heartbeat_last_tick_at="+str(payload["observed_at"]))
PY

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

# Generic heartbeat generation includes read-only social observation scheduling.
