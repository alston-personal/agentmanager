#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_social_action_runtime=WRONG_USER"; exit 2; }
PERSONA_PATH="${PERSONA_PATH:-personas/sunlake-milkcat}"
SOCIAL_EXECUTOR="${AGENTOS_PERSONA_SOCIAL_EXECUTOR:-$HOME/.local/lib/agentos/persona_social_executor.py}"
REPLY_INTENT_GENERATOR="${AGENTOS_PERSONA_REPLY_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_reply_intent_generator.py}"
POST_INTENT_GENERATOR="${AGENTOS_PERSONA_POST_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_post_intent_generator.py}"
GROWTH_METRICS="${AGENTOS_PERSONA_GROWTH_METRICS:-$HOME/.local/lib/agentos/persona_growth_metrics_collector.py}"
LOCK=/tmp/agentos-persona-pdca-heartbeat.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "persona_social_action_runtime=BUSY"
  exit 0
fi

test -f "$SOCIAL_EXECUTOR"
test -f "$REPLY_INTENT_GENERATOR"
test -f "$POST_INTENT_GENERATOR"
test -f "$GROWTH_METRICS"
command -v gh >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth status >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth setup-git >/dev/null

DATA_REPO="$(mktemp -d /tmp/persona-social-data-XXXXXX)"
cleanup() { rm -rf "$DATA_REPO"; }
trap cleanup EXIT

env -u GH_TOKEN -u GITHUB_TOKEN gh repo clone alston-personal/my-agent-data "$DATA_REPO" -- --branch main --single-branch >/dev/null
git -C "$DATA_REPO" config --unset-all credential.helper || true
git -C "$DATA_REPO" config credential.https://github.com.helper '!/usr/bin/gh auth git-credential'

ROOT="$DATA_REPO/$PERSONA_PATH"
test -f "$ROOT/pdca/state.json"
test -f "$ROOT/events/events.jsonl"

# Fail closed on durable-state corruption. A malformed persona state must be
# reported as DEGRADED before any adapter/cognition work can consume it.
if ! python3 - "$ROOT/pdca/state.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
try:
    json.loads(p.read_text(encoding="utf-8"))
except (OSError,json.JSONDecodeError) as exc:
    print("persona_social_state_integrity=DEGRADED error="+type(exc).__name__)
    raise SystemExit(3)
print("persona_social_state_integrity=PASS")
PY
then
  echo "persona_social_action_runtime=DEGRADED_STATE" >&2
  exit 3
fi

# Resolve the PDCA-selected read before cognition. This is the existing worker
# lane consuming a durable intent, not another independent patrol cron.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SOCIAL_RECEIPT="$ROOT/pdca/social_receipts/$STAMP.json"
mkdir -p "$(dirname "$SOCIAL_RECEIPT")"
python3 "$SOCIAL_EXECUTOR" --persona-dir "$ROOT" --username mio.milkcat --receipt-out "$SOCIAL_RECEIPT"
python3 -m json.tool "$SOCIAL_RECEIPT" >/dev/null

# Social lane owns bounded social cognition. A reasoning defer/failure is local
# to this lane and never blocks the core PDCA/Observer heartbeat.
if python3 "$REPLY_INTENT_GENERATOR" --persona-dir "$ROOT"; then
  echo "persona_social_reply_intent=PASS"
else
  echo "persona_social_reply_intent=DEGRADED rc=$?" >&2
fi
if python3 "$POST_INTENT_GENERATOR" --persona-dir "$ROOT"; then
  echo "persona_social_post_intent=PASS"
else
  echo "persona_social_post_intent=DEGRADED rc=$?" >&2
fi
METRICS_RECEIPT="$ROOT/pdca/growth_metrics/$STAMP.json"
mkdir -p "$(dirname "$METRICS_RECEIPT")"
if python3 "$GROWTH_METRICS" --persona-dir "$ROOT" --username mio.milkcat --receipt-out "$METRICS_RECEIPT"; then
  python3 -m json.tool "$METRICS_RECEIPT" >/dev/null
else
  # A metrics outage must not discard the observation or incident in this clone.
  python3 - "$METRICS_RECEIPT" <<'PY'
import json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"status":"ERROR","changed":0})+"\n",encoding="utf-8")
PY
fi

STATUS="$(python3 -c "import json; print(json.load(open('$SOCIAL_RECEIPT')).get('status',''))")"
if [ "$STATUS" = "NO_ACTION" ]; then
  rm -f "$SOCIAL_RECEIPT"
fi

cd "$DATA_REPO"
git config user.name 'agentos-persona-social[bot]'
git config user.email 'agentos-persona-social[bot]@users.noreply.github.com'
git add "$PERSONA_PATH/pdca" "$PERSONA_PATH/events/events.jsonl"
if git diff --cached --quiet; then
  echo "persona_social_action_runtime=NO_ACTION"
  exit 0
fi

git commit -m "persona(mio): persist autonomous social action" >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' push >/dev/null

if [ "$STATUS" = "NO_ACTION" ]; then
  python3 - "$METRICS_RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
print("persona_social_action_runtime=METRICS_ONLY")
print("persona_growth_metrics_status="+str(r.get("status") or "unknown"))
print("persona_growth_metrics_changed="+str(r.get("changed") or 0))
PY
else
  python3 - "$SOCIAL_RECEIPT" "$METRICS_RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
m=json.load(open(sys.argv[2],encoding="utf-8"))
assert r.get("status") in ("EXECUTED","BLOCKED"),r
print("persona_social_action_runtime="+("PASS" if r.get("ok") is True else "BLOCKED"))
print("persona_social_action_capability="+str(r.get("capability") or "unknown"))
print("persona_social_action_write="+str(bool(r.get("write_performed"))).lower())
print("persona_growth_metrics_status="+str(m.get("status") or "unknown"))
print("persona_growth_metrics_changed="+str(m.get("changed") or 0))
PY
fi
