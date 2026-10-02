#!/usr/bin/env bash
set -euo pipefail

PROFILE="${HOME}/.config/agentos/personas/oursong_alstonhuang.env"
TIMER="agentos-persona-social@oursong_alstonhuang.timer"
STATE="${HOME}/agent-data/personas/oursong_alstonhuang/pdca/state.json"
CURRENT="${HOME}/.local/share/agentos/persona-social/current-oursong_alstonhuang"

test -f "${PROFILE}"
test -L "${CURRENT}"
RELEASE="$(readlink -f "${CURRENT}")"
test -d "${RELEASE}"

set -a
# shellcheck disable=SC1090
source "${PROFILE}"
set +a

test "${AGENTOS_PERSONA_SLUG:-}" = "oursong_alstonhuang"
test "${AGENTOS_PERSONA_ID:-}" = "oursong-alstonhuang-001"
test -f "${AGENTOS_PERSONA_SOCIAL_LOOP_SCRIPT:-}"
test -f "${AGENTOS_PERSONA_PDCA_SYNC_SCRIPT:-}"

case "${AGENTOS_PERSONA_SOCIAL_LOOP_SCRIPT}" in
  "${RELEASE}"/*) ;;
  *) echo "oursong_status=UNPINNED_SOCIAL_LOOP"; exit 3 ;;
esac
case "${AGENTOS_PERSONA_PDCA_SYNC_SCRIPT}" in
  "${RELEASE}"/*) ;;
  *) echo "oursong_status=UNPINNED_PDCA_SYNC"; exit 4 ;;
esac

systemctl --user is-enabled --quiet "${TIMER}"
systemctl --user is-active --quiet "${TIMER}"

test -f "${STATE}"
python3 - "${STATE}" "${RELEASE}" <<'PY'
import json,re,sys
from pathlib import Path
state_path=Path(sys.argv[1]); release=Path(sys.argv[2])
state=json.loads(state_path.read_text(encoding='utf-8'))
assert state.get('persona_id')=='oursong-alstonhuang-001',state
cycle=int(state.get('cycle') or 0)
status=str(state.get('status') or '')
commit=release.name
assert re.fullmatch(r'[0-9a-f]{40}',commit),commit
print('oursong_status=PASS')
print('oursong_runtime_release='+str(release))
print('oursong_runtime_source_commit='+commit)
print('oursong_pdca_cycle='+str(cycle))
print('oursong_pdca_status='+status)
print('oursong_last_tick_at='+str(state.get('last_tick_at')))
print('oursong_last_action_at='+str(state.get('last_action_at')))
PY

systemctl --user show "${TIMER}"   -p ActiveState   -p UnitFileState   -p LastTriggerUSec   -p NextElapseUSecRealtime   --no-pager
