#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_pdca_runtime=WRONG_USER"; exit 2; }
PERSONA_PATH="${PERSONA_PATH:-personas/sunlake-milkcat}"
TICK="${AGENTOS_PERSONA_PDCA_TICK:-$HOME/.local/lib/agentos/persona_pdca_tick.py}"
SOCIAL_EXECUTOR="${AGENTOS_PERSONA_SOCIAL_EXECUTOR:-$HOME/.local/lib/agentos/persona_social_executor.py}"
INTERNAL_EXECUTOR="${AGENTOS_PERSONA_INTERNAL_EXECUTOR:-$HOME/.local/lib/agentos/persona_internal_activity_executor.py}"
REPLY_INTENT_GENERATOR="${AGENTOS_PERSONA_REPLY_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_reply_intent_generator.py}"
POST_INTENT_GENERATOR="${AGENTOS_PERSONA_POST_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_post_intent_generator.py}"
LOCK=/tmp/agentos-persona-pdca-heartbeat.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "persona_pdca_runtime=BUSY"
  exit 0
fi

test -f "$TICK"
test -f "$SOCIAL_EXECUTOR"
test -f "$INTERNAL_EXECUTOR"
test -f "$REPLY_INTENT_GENERATOR"
test -f "$POST_INTENT_GENERATOR"
command -v gh >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth status >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth setup-git >/dev/null

DATA_REPO="$(mktemp -d /tmp/persona-agent-data-XXXXXX)"
RECEIPT="$(mktemp /tmp/persona-pdca-receipt-XXXXXX.json)"
cleanup() { rm -rf "$DATA_REPO" "$RECEIPT"; }
trap cleanup EXIT

env -u GH_TOKEN -u GITHUB_TOKEN gh repo clone alston-personal/my-agent-data "$DATA_REPO" -- --branch main --single-branch >/dev/null
git -C "$DATA_REPO" config --unset-all credential.helper || true
git -C "$DATA_REPO" config credential.https://github.com.helper '!/usr/bin/gh auth git-credential'

test -f "$DATA_REPO/$PERSONA_PATH/persona_state.json"
test -f "$DATA_REPO/$PERSONA_PATH/ir/current.json"
test -f "$DATA_REPO/$PERSONA_PATH/pdca/config.json"

python3 "$TICK" --persona-dir "$DATA_REPO/$PERSONA_PATH" --receipt-out "$RECEIPT" --trigger oracle_local_timer
python3 -m json.tool "$RECEIPT" >/dev/null
python3 "$INTERNAL_EXECUTOR" --persona-dir "$DATA_REPO/$PERSONA_PATH"
python3 "$REPLY_INTENT_GENERATOR" --persona-dir "$DATA_REPO/$PERSONA_PATH"
python3 "$POST_INTENT_GENERATOR" --persona-dir "$DATA_REPO/$PERSONA_PATH"
SOCIAL_RECEIPT="$DATA_REPO/$PERSONA_PATH/pdca/social_receipts/$(date -u +%Y%m%dT%H%M%SZ).json"
mkdir -p "$(dirname "$SOCIAL_RECEIPT")"
python3 "$SOCIAL_EXECUTOR" --persona-dir "$DATA_REPO/$PERSONA_PATH" --username mio.milkcat --receipt-out "$SOCIAL_RECEIPT"
python3 -m json.tool "$SOCIAL_RECEIPT" >/dev/null

cd "$DATA_REPO"
git config user.name 'agentos-persona-pdca[bot]'
git config user.email 'agentos-persona-pdca[bot]@users.noreply.github.com'
git add "$PERSONA_PATH/pdca" "$PERSONA_PATH/events/events.jsonl"
if ! git diff --cached --quiet; then
  CYCLE="$(python3 -c "import json; print(json.load(open('$PERSONA_PATH/pdca/state.json'))['cycle'])")"
  git commit -m "persona(mio): persist autonomous PDCA cycle $CYCLE" >/dev/null
  env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' push >/dev/null
fi

python3 - "$DATA_REPO/$PERSONA_PATH" "$RECEIPT" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); receipt=Path(sys.argv[2])
s=json.load(open(p/"pdca/state.json",encoding="utf-8"))
last=json.load(open(receipt,encoding="utf-8"))
assert s["status"]=="RUNNING",s
assert int(s["cycle"])>=1,s
assert last["cycle"]==s["cycle"],(last,s)
assert last["truth_boundary"]["external_receipt_required"] is True
print(f"persona_pdca_runtime=PASS cycle={s['cycle']} intent={last['plan']['selected_intent']}")
PY
