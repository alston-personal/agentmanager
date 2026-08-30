#!/usr/bin/env bash
set -uo pipefail

SHA="${1:?service sha required}"
BASE=/home/ubuntu/vendor-reputation-service
ERR=/tmp/vendor-patrol-stage.err
OUT=/tmp/vendor-patrol-worker.out
: >"$ERR"
: >"$OUT"

emit_failure() {
  local stage="$1" rc="$2" file="${3:-$ERR}"
  python3 - "$stage" "$rc" "$file" "${SOC_THREADS_TOKEN:-}" <<'PY'
import json,pathlib,re,sys
stage,rc,path,token=sys.argv[1],int(sys.argv[2]),sys.argv[3],sys.argv[4]
p=pathlib.Path(path)
text=p.read_text(errors='replace') if p.exists() else ''
if token:
    text=text.replace(token,'[REDACTED_TOKEN]')
text=re.sub(r'access_token=[^&\s]+','access_token=[REDACTED]',text)
text=' '.join(text.split())[-800:]
print(json.dumps({
  'schema':'milkcat.vendor-threads-patrol-receipt/v3',
  'ok':False,
  'failed_stage':stage,
  'worker_exit_code':rc if stage == 'worker' else None,
  'queries':0,
  'results_seen':0,
  'new_candidates':0,
  'duplicates':0,
  'errors':1,
  'by_search_type':{},
  'error_signatures':[],
  'candidate_sources_total':None,
  'candidate_authors_total':None,
  'sanitized_error_tail':text,
  'raw_text_emitted':False,
  'token_exposed':False,
  'reviews_published':False,
  'core_modified':False
},ensure_ascii=False))
PY
  exit "$rc"
}

if [ ! -d "$BASE/.git" ]; then echo 'service git repo missing' >"$ERR"; emit_failure repo 2; fi
git -C "$BASE" fetch --depth=1 origin "$SHA" >"$ERR" 2>&1 || emit_failure fetch $?
git -C "$BASE" checkout --detach "$SHA" >"$ERR" 2>&1 || emit_failure checkout $?

set -a
. /home/ubuntu/agent-data/secrets/vendor-reputation.env 2>"$ERR" || emit_failure vendor_env $?
set +a

SOC_THREADS_TOKEN=$(python3 - <<'PY'
from pathlib import Path
p=Path('/home/ubuntu/agent-data/secrets/zeus-writer.env')
value=''
for line in p.read_text().splitlines():
    if line.startswith('SOC_THREADS_TOKEN='):
        value=line.split('=',1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value=value[1:-1]
        break
if not value:
    raise SystemExit('SOC_THREADS_TOKEN missing')
print(value)
PY
) || emit_failure threads_token $?
export SOC_THREADS_TOKEN

cd "$BASE" || emit_failure chdir $?
docker compose up -d --build >"$ERR" 2>&1 || emit_failure compose $?
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/003_source_discovery.sql >"$ERR" 2>&1 || emit_failure migration $?

set +e
docker compose run --rm -T -e SOC_THREADS_TOKEN="$SOC_THREADS_TOKEN" api \
  python /srv/app/scripts/discover_threads_sources.py /srv/app/config/threads_discovery_queries.txt \
  < /dev/null >"$OUT" 2>"$ERR"
WORKER_RC=$?
set -e
if [ "$WORKER_RC" -ne 0 ]; then emit_failure worker "$WORKER_RC" "$ERR"; fi

CANDIDATES=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(*) from candidate_sources where status='candidate';" 2>"$ERR" | tr -d '\r') || emit_failure db_count $?
AUTHORS=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(distinct source_author) from candidate_sources where status='candidate' and source_author is not null;" 2>"$ERR" | tr -d '\r') || emit_failure db_count $?

python3 - "$OUT" "$CANDIDATES" "$AUTHORS" <<'PY'
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])
x=json.loads(p.read_text())
print(json.dumps({
  'schema':'milkcat.vendor-threads-patrol-receipt/v3',
  'ok':True,
  'failed_stage':None,
  'worker_exit_code':0,
  'queries':x.get('queries',0),
  'results_seen':x.get('results',0),
  'new_candidates':x.get('new_candidates',0),
  'duplicates':x.get('duplicates',0),
  'errors':x.get('errors',0),
  'by_search_type':x.get('by_search_type',{}),
  'error_signatures':x.get('error_signatures',[]),
  'candidate_sources_total':int(sys.argv[2]),
  'candidate_authors_total':int(sys.argv[3]),
  'sanitized_error_tail':'',
  'raw_text_emitted':False,
  'token_exposed':False,
  'reviews_published':False,
  'core_modified':False
},ensure_ascii=False))
PY
