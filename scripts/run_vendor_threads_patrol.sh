#!/usr/bin/env bash
set -uo pipefail

SHA="${1:?service sha required}"
BASE=/home/ubuntu/vendor-reputation-service
ERR=/tmp/vendor-patrol-stage.err
OUT=/tmp/vendor-patrol-worker.out
REPUTATION_OUT=/tmp/vendor-reputation-recompute.out
VENDOR_ENV=/home/ubuntu/agent-data/secrets/vendor-reputation.env
: >"$ERR"
: >"$OUT"
: >"$REPUTATION_OUT"

emit_failure() {
  local stage="$1" rc="$2" file="${3:-$ERR}"
  python3 - "$stage" "$rc" "$file" "${SOC_THREADS_TOKEN:-}" "${VENDOR_ADMIN_TOKEN:-}" <<'PY'
import json,pathlib,re,sys
stage,rc,path,threads_token,admin_token=sys.argv[1],int(sys.argv[2]),sys.argv[3],sys.argv[4],sys.argv[5]
p=pathlib.Path(path)
text=p.read_text(errors='replace') if p.exists() else ''
for token in (threads_token, admin_token):
    if token:
        text=text.replace(token,'[REDACTED_TOKEN]')
text=re.sub(r'access_token=[^&\s]+','access_token=[REDACTED]',text)
text=' '.join(text.split())[-800:]
print(json.dumps({
  'schema':'milkcat.vendor-threads-patrol-receipt/v6',
  'ok':False,'failed_stage':stage,
  'worker_exit_code':rc if stage == 'worker' else None,
  'queries':0,'results_seen':0,'direct_results':0,'harvest_results':0,
  'harvest_vendor_matches':0,'harvest_filtered_out':0,
  'new_candidates':0,'duplicates':0,
  'actor_observations':0,'same_actor_multiple_sources':0,'same_actor_repeated_text':0,
  'reputation_vendors_computed':0,'reputation_reviews_seen':0,
  'reputation_independent_voices':0,'reputation_duplicate_actor_reviews_collapsed':0,
  'errors':1,
  'by_search_type':{},'harvest_by_search_type':{},'positive_controls':[],'error_signatures':[],
  'candidate_sources_total':None,'candidate_authors_total':None,
  'sanitized_error_tail':text,'raw_text_emitted':False,'raw_text_persisted':False,
  'token_exposed':False,'reviews_published':False,'core_modified':False
},ensure_ascii=False))
PY
  exit "$rc"
}

if [ ! -d "$BASE/.git" ]; then echo 'service git repo missing' >"$ERR"; emit_failure repo 2; fi
git -C "$BASE" fetch --depth=1 origin "$SHA" >"$ERR" 2>&1 || emit_failure fetch $?
git -C "$BASE" checkout --detach "$SHA" >"$ERR" 2>&1 || emit_failure checkout $?

if [ ! -f "$VENDOR_ENV" ]; then
  echo 'vendor env missing' >"$ERR"
  emit_failure vendor_env 2
fi

if ! grep -q '^VENDOR_ADMIN_TOKEN=' "$VENDOR_ENV"; then
  ADMIN_TOKEN=$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
) || emit_failure admin_token_generate $?
  umask 077
  printf '\nVENDOR_ADMIN_TOKEN=%s\n' "$ADMIN_TOKEN" >> "$VENDOR_ENV" || emit_failure admin_token_write $?
  chmod 600 "$VENDOR_ENV" || emit_failure admin_token_permissions $?
  unset ADMIN_TOKEN
fi

set -a
. "$VENDOR_ENV" 2>"$ERR" || emit_failure vendor_env $?
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

docker compose up -d db >"$ERR" 2>&1 || emit_failure compose_db $?
READY=0
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U vendor_service -d vendor_reputation >/dev/null 2>"$ERR"; then
    READY=1
    break
  fi
  sleep 1
done
if [ "$READY" -ne 1 ]; then echo 'vendor db did not become ready' >"$ERR"; emit_failure db_ready 2; fi

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/003_source_discovery.sql >"$ERR" 2>&1 || emit_failure migration_003 $?
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/004_actor_independence.sql >"$ERR" 2>&1 || emit_failure migration_004 $?
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/005_reputation_snapshot_voice_counts.sql >"$ERR" 2>&1 || emit_failure migration_005 $?

docker compose up -d --build api >"$ERR" 2>&1 || emit_failure compose_api $?

set +e
docker compose run --rm -T -e SOC_THREADS_TOKEN="$SOC_THREADS_TOKEN" api \
  python /srv/app/scripts/discover_threads_sources.py /srv/app/config/threads_discovery_queries.txt \
  < /dev/null >"$OUT" 2>"$ERR"
WORKER_RC=$?
set -e
if [ "$WORKER_RC" -ne 0 ]; then emit_failure worker "$WORKER_RC" "$ERR"; fi

set +e
docker compose run --rm -T api \
  python /srv/app/scripts/recompute_reputation.py \
  < /dev/null >"$REPUTATION_OUT" 2>"$ERR"
REPUTATION_RC=$?
set -e
if [ "$REPUTATION_RC" -ne 0 ]; then emit_failure reputation_recompute "$REPUTATION_RC" "$ERR"; fi

CANDIDATES=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(*) from candidate_sources where status='candidate';" 2>"$ERR" | tr -d '\r') || emit_failure db_count $?
AUTHORS=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(distinct source_author) from candidate_sources where status='candidate' and source_author is not null;" 2>"$ERR" | tr -d '\r') || emit_failure db_count $?

python3 - "$OUT" "$REPUTATION_OUT" "$CANDIDATES" "$AUTHORS" <<'PY'
import json,pathlib,sys
x=json.loads(pathlib.Path(sys.argv[1]).read_text())
r=json.loads(pathlib.Path(sys.argv[2]).read_text())
print(json.dumps({
  'schema':'milkcat.vendor-threads-patrol-receipt/v6',
  'ok':True,'failed_stage':None,'worker_exit_code':0,
  'queries':x.get('queries',0),'results_seen':x.get('results',0),
  'direct_results':x.get('direct_results',0),'harvest_results':x.get('harvest_results',0),
  'harvest_vendor_matches':x.get('harvest_vendor_matches',0),
  'harvest_filtered_out':x.get('harvest_filtered_out',0),
  'new_candidates':x.get('new_candidates',0),'duplicates':x.get('duplicates',0),
  'actor_observations':x.get('actor_observations',0),
  'same_actor_multiple_sources':x.get('same_actor_multiple_sources',0),
  'same_actor_repeated_text':x.get('same_actor_repeated_text',0),
  'reputation_vendors_computed':r.get('vendors_computed',0),
  'reputation_reviews_seen':r.get('reviews_seen',0),
  'reputation_independent_voices':r.get('independent_voices',0),
  'reputation_duplicate_actor_reviews_collapsed':r.get('duplicate_actor_reviews_collapsed',0),
  'errors':x.get('errors',0),
  'by_search_type':x.get('by_search_type',{}),'harvest_by_search_type':x.get('harvest_by_search_type',{}),
  'positive_controls':x.get('positive_controls',[]),'error_signatures':x.get('error_signatures',[]),
  'candidate_sources_total':int(sys.argv[3]),'candidate_authors_total':int(sys.argv[4]),
  'sanitized_error_tail':'','raw_text_emitted':False,
  'raw_text_persisted':bool(x.get('raw_text_persisted',False)),
  'token_exposed':False,'reviews_published':False,'core_modified':False
},ensure_ascii=False))
PY
