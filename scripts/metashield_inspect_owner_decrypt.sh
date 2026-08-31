#!/usr/bin/env bash
set -u
ROOT=/home/ubuntu/metashield-protocol

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "branch=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
echo "head=$(git -C "$ROOT" rev-parse HEAD)"

echo '===== exact error sources ====='
grep -Rni --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=.git -F 'Owner decryption failed' "$ROOT" 2>/dev/null | sed -n '1,120p' || true
grep -Rni --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=.git -E 'owner.*decrypt|decrypt.*owner|DECRYPT_ECHO_CONTENT|ownerKeyEnvelope|sharingKeyId' "$ROOT/extension" "$ROOT/web-feed" 2>/dev/null | sed -n '1,360p' || true

echo '===== recent echo decrypt errors ====='
python3 - <<'PY'
import json, pathlib
p=pathlib.Path('/home/ubuntu/metashield-protocol/memory/dev-errors.ndjson')
if not p.exists():
    print('dev_errors_missing')
else:
    rows=[]
    for line in p.read_text(errors='replace').splitlines():
        try: d=json.loads(line)
        except Exception: continue
        if d.get('source')=='echo:decrypt' or 'decrypt' in str(d.get('source','')).lower() or 'decrypt' in str(d.get('message','')).lower():
            rows.append(d)
    for d in rows[-40:]:
        # redact any accidental secrets; keep only structural evidence
        out={k:d.get(k) for k in ('timestamp','source','message','url') if k in d}
        details=d.get('details') or {}
        out['details']={k:details.get(k) for k in ('txId','mediaIndex','mediaTotal','sharingKeyId','requesterKeyId','identityKey','identityAlias') if k in details}
        print(json.dumps(out, ensure_ascii=False))
PY

echo '===== recent backup receipts metadata ====='
python3 - <<'PY'
import json, pathlib
p=pathlib.Path('/home/ubuntu/metashield-protocol/memory/backup-receipts.ndjson')
if p.exists():
  rows=[]
  for line in p.read_text(errors='replace').splitlines():
    try:d=json.loads(line)
    except Exception:continue
    rows.append(d)
  for d in rows[-20:]:
    out={k:d.get(k) for k in ('timestamp','txId','platform','identity_alias','identity_key','sharing_key_id','extension_version') if k in d}
    print(json.dumps(out,ensure_ascii=False))
PY

echo '===== local extension identity metadata files ====='
find "$ROOT" -maxdepth 4 -type f \( -iname '*identity*.json' -o -iname '*wallet*.json' -o -iname '*key*.json' \) 2>/dev/null | sed -n '1,120p'

echo '===== extension decrypt implementation snippets ====='
for f in "$ROOT"/extension/*.js "$ROOT"/extension/**/*.js; do
  test -f "$f" || continue
  if grep -qE 'DECRYPT_ECHO_CONTENT|Owner decryption failed|ownerKeyEnvelope' "$f"; then
    echo "--- $f"
    grep -nE 'DECRYPT_ECHO_CONTENT|Owner decryption failed|ownerKeyEnvelope|sharingKeyId|unwrap|decrypt' "$f" | sed -n '1,220p'
  fi
done
