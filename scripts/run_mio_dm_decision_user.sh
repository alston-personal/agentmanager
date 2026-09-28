#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_dm_decision=WRONG_USER" >&2
  exit 2
fi

RUN_ID="${AGENTOS_DM_SOURCE_RUN_ID:-}"
USERNAME="${AGENTOS_DM_USERNAME:-}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
REPO="${AGENTOS_REPO:-$HOME/agentmanager}"

printf '%s' "$RUN_ID" | grep -Eq '^[0-9]{1,20}$'
[ "$USERNAME" = "0__0.ayoub" ]
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

env -u GH_TOKEN -u GITHUB_TOKEN gh run download "$RUN_ID"   -R alston-personal/agentmanager   -n threads-native-read   -D "$TMP/artifact" >/dev/null

test -f "$TMP/artifact/threads-native-read.json"

python3 - "$TMP/artifact/threads-native-read.json" "$USERNAME" > "$TMP/dm.json" <<'PY'
import json,sys
doc=json.load(open(sys.argv[1],encoding='utf-8'))
user=sys.argv[2]
lines=[x.strip() for x in str(doc.get('visible_text') or '').splitlines()]
try:
    i=lines.index(user)
except ValueError:
    raise SystemExit('target DM preview not found')
preview=''
for x in lines[i+1:i+6]:
    if x and x!='·' and not x.endswith('天') and not x.endswith('小時') and not x.endswith('分鐘'):
        preview=x
        break
if not preview:
    raise SystemExit('target DM preview empty')
print(json.dumps({
    'platform':'threads',
    'account':'mio.milkcat',
    'sender':user,
    'message':preview,
    'context_scope':'inbox_preview',
    'relationship_status':'unknown_new_interaction',
},ensure_ascii=False))
PY

git -C "$REPO" show "$SOURCE_COMMIT:scripts/mio_persona_dm_decision_user.py" > "$TMP/decide.py"
chmod 0700 "$TMP/decide.py"

AGENTOS_MIO_RELAY_ROOT="$HOME/agent-data/runtime/mio-antigravity-relay" PYTHONPATH="$REPO" python3 "$TMP/decide.py" < "$TMP/dm.json" > "$TMP/decision.json"

python3 - "$TMP/decision.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
assert d.get('decision') in ('reply','no_reply')
if d['decision']=='reply':
    assert isinstance(d.get('text'),str) and d['text'].strip()
else:
    assert d.get('text') in (None,'')
print('mio_dm_decision=PASS:'+d['decision'])
print('mio_dm_decision_payload='+json.dumps(d,ensure_ascii=False,separators=(',',':')))
PY
