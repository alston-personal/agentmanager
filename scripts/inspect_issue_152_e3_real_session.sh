#!/usr/bin/env bash
set -euo pipefail

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_REF="core/issue-152-executor-awareness"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"

test -d "$REPO/.git" || { echo "ERROR: AgentOS repo missing: $REPO" >&2; exit 3; }

git -C "$REPO" fetch --no-tags origin "$SOURCE_REF" >/dev/null
SOURCE_COMMIT="$(git -C "$REPO" rev-parse FETCH_HEAD)"

echo "agentos_e3_inspector_source_commit=$SOURCE_COMMIT"
echo "agentos_e3_attestation_path=$DATA_ROOT/runtime/antigravity-preinvocation-last.json"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
git -C "$REPO" show "$SOURCE_COMMIT:scripts/inspect_antigravity_preinvocation_attestation.py" > "$TMP"

set +e
AGENT_DATA_ROOT="$DATA_ROOT" python3 "$TMP"
RC=$?
set -e

case "$RC" in
  0)
    echo "agentos_e3_real_session_hook=FIRED_AND_HYDRATED"
    ;;
  5)
    echo "agentos_e3_real_session_hook=FIRED_AND_HYDRATED_IDENTITY_UNBOUND"
    ;;
  6)
    echo "agentos_e3_real_session_hook=FIRED_HYDRATION_GENERATION_MISMATCH"
    ;;
  7)
    echo "agentos_e3_real_session_hook=FIRED_NO_INJECTION"
    ;;
  4)
    echo "agentos_e3_real_session_hook=NOT_PROVEN"
    ;;
  *)
    echo "agentos_e3_real_session_hook=INSPECTION_ERROR"
    ;;
esac
exit "$RC"
