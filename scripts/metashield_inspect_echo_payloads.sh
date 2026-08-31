#!/usr/bin/env bash
set -euo pipefail
ALIAS=${1:-sunlake}
PLATFORM=${2:-all}
API=https://studio.milkcat.org/chamber-api
IRYS_INDEX=https://devnet.irys.xyz
IRYS_DATA=https://gateway.irys.xyz

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "alias=$ALIAS platform=$PLATFORM"

curl -fsS --max-time 20 "$API/identity/resolve?alias=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$ALIAS")&platform=$PLATFORM" -o /tmp/identity-resolve.json
python3 - <<'PY'
import json
p=json.load(open('/tmp/identity-resolve.json'))
print('identity_resolve=', {k:p.get(k) for k in ('success','alias','contentKey','currentWallet','displayName')})
PY
CONTENT_KEY=$(python3 - <<'PY'
import json
p=json.load(open('/tmp/identity-resolve.json'))
print(p.get('contentKey') or '')
PY
)
test -n "$CONTENT_KEY"
export CONTENT_KEY
python3 - <<'PY' >/tmp/query.json
import json, os
key=os.environ['CONTENT_KEY']
q='''query { transactions(tags: [{ name: "App-Name", values: ["Chamber"] }, { name: "Identity-Key", values: ["%s"] }], first: 20) { edges { node { id tags { name value } } } } }''' % key
print(json.dumps({'query':q}))
PY
curl -fsS --max-time 30 -H 'content-type: application/json' --data @/tmp/query.json "$IRYS_INDEX/graphql" -o /tmp/echo-graphql.json

python3 - <<'PY'
import json
j=json.load(open('/tmp/echo-graphql.json'))
edges=((j.get('data') or {}).get('transactions') or {}).get('edges') or []
rows=[]
for e in edges:
 n=e['node']; tags={t['name']:t['value'] for t in n.get('tags',[])}
 rows.append((int(tags.get('Backup-Time') or 0), n['id'], tags))
rows.sort(reverse=True)
open('/tmp/txids.txt','w').write('\n'.join(r[1] for r in rows))
print('transaction_count=',len(rows))
for bt,tx,tags in rows:
 print('TX',tx,'backup_time=',bt,'platform=',tags.get('Platform'),'ext_tag=',tags.get('Extension-Version'),'enc_tag=',tags.get('Encryption-Version'))
PY

echo '===== payload metadata ====='
while read -r tx; do
  test -n "$tx" || continue
  if ! curl -fsS --max-time 30 "$IRYS_DATA/$tx" -o "/tmp/tx-$tx.json"; then
    echo "TX $tx fetch=FAIL"
    continue
  fi
  TX="$tx" python3 - <<'PY'
import json, os
p=json.load(open('/tmp/tx-'+os.environ['TX']+'.json'))
env=p.get('key_envelope') or {}
media=p.get('media') or {}
print(json.dumps({
 'txId':os.environ['TX'],
 'protocol_version':p.get('protocol_version'),
 'extension_version':p.get('extension_version'),
 'encryption_version':p.get('encryption_version'),
 'is_encrypted':p.get('is_encrypted'),
 'key_envelope_present':bool(p.get('key_envelope')),
 'key_envelope_version':env.get('version'),
 'key_envelope_algorithm':env.get('algorithm'),
 'identity_key':p.get('identity_key'),
 'identity_alias':p.get('identity_alias'),
 'platform':p.get('platform'),
 'backup_timestamp':p.get('backup_timestamp'),
 'source_url':p.get('source_url'),
 'media_items':len(media.get('items') or []),
}, ensure_ascii=False))
PY
done </tmp/txids.txt
