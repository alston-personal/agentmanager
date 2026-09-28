#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" = "1001" ] || { echo "persona_post_nudge=WRONG_USER"; exit 2; }
PERSONA_PATH="${PERSONA_PATH:-personas/sunlake-milkcat}"
POST_GENERATOR="${AGENTOS_PERSONA_POST_INTENT_GENERATOR:-$HOME/.local/lib/agentos/persona_post_intent_generator.py}"
SOCIAL_EXECUTOR="${AGENTOS_PERSONA_SOCIAL_EXECUTOR:-$HOME/.local/lib/agentos/persona_social_executor.py}"
LOCK=/tmp/agentos-persona-pdca-heartbeat.lock

exec 9>"$LOCK"
flock -n 9 || { echo "persona_post_nudge=BUSY"; exit 3; }

DATA_REPO="$(mktemp -d /tmp/persona-post-nudge-XXXXXX)"
cleanup(){ rm -rf "$DATA_REPO"; }
trap cleanup EXIT

env -u GH_TOKEN -u GITHUB_TOKEN gh auth status >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth setup-git >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh repo clone alston-personal/my-agent-data "$DATA_REPO" -- --branch main --single-branch >/dev/null
git -C "$DATA_REPO" config --unset-all credential.helper || true
git -C "$DATA_REPO" config credential.https://github.com.helper '!/usr/bin/gh auth git-credential'

ROOT="$DATA_REPO/$PERSONA_PATH"
test -f "$ROOT/pdca/state.json"
test -f "$POST_GENERATOR"
test -f "$SOCIAL_EXECUTOR"

python3 "$POST_GENERATOR" --persona-dir "$ROOT" | tee /tmp/persona-post-nudge-generator.json

python3 - "$ROOT/pdca/state.json" <<'PY'
import json,sys
from datetime import datetime,timezone
p=sys.argv[1]
s=json.load(open(p,encoding="utf-8"))
pending=s.get("pending_external_actions") or []
pub=next((x for x in pending if isinstance(x,dict) and x.get("capability")=="social.post.publish" and x.get("status")=="candidate"),None)
if not pub:
    raise SystemExit("persona_post_nudge=NO_PUBLISH_CANDIDATE")
pub["not_before"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
pub["execution_context"]="owner_requested_immediate_observation"
with open(p,"w",encoding="utf-8") as f:
    json.dump(s,f,ensure_ascii=False,indent=2); f.write("\n")
print("persona_post_nudge_candidate="+str(pub.get("action_id")))
print("persona_post_nudge_text="+str(pub.get("primary_text") or ""))
PY

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECEIPT="$ROOT/pdca/social_receipts/$STAMP-owner-nudge.json"
mkdir -p "$(dirname "$RECEIPT")"
python3 "$SOCIAL_EXECUTOR" --persona-dir "$ROOT" --username mio.milkcat --receipt-out "$RECEIPT"
python3 -m json.tool "$RECEIPT" >/dev/null

python3 - "$RECEIPT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1],encoding="utf-8"))
assert r.get("ok") is True,r
assert r.get("status")=="EXECUTED",r
assert r.get("capability")=="social.post.publish",r
assert r.get("write_performed") is True,r
res=r.get("provider_receipt") or {}
item=res.get("result") or {}
oid=item.get("id") or item.get("object_id")
assert oid,r
print("persona_post_nudge=PASS")
print("persona_post_id="+str(oid))
if item.get("permalink"): print("persona_post_permalink="+str(item["permalink"]))
PY

cd "$DATA_REPO"
git config user.name 'agentos-persona-social[bot]'
git config user.email 'agentos-persona-social[bot]@users.noreply.github.com'
git add "$PERSONA_PATH/pdca" "$PERSONA_PATH/events/events.jsonl"
git commit -m "persona(mio): persist owner-nudged autonomous post" >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' push >/dev/null
