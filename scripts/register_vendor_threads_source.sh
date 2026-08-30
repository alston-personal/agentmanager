#!/usr/bin/env bash
set -euo pipefail

SHA="$1"
INPUT="$2"
DIR=/home/ubuntu/vendor-reputation-service
cd "$DIR"

git fetch --depth=1 origin "$SHA" >/dev/null 2>&1
git checkout --detach "$SHA" >/dev/null 2>&1

# Ensure both the source registry and the canonical post-identity invariant are
# present before resolving/upserting the incoming source.
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/002_source_registry.sql >/dev/null
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/006_threads_source_identity.sql >/dev/null

FINAL=$(curl -LsS --max-time 30 -o /dev/null -w '%{url_effective}' "$INPUT" || true)
mapfile -t IDENTITY < <(python3 - "$FINAL" <<'PY'
import re,sys,urllib.parse
value=sys.argv[1].strip()
canonical=''
object_id=''
try:
    p=urllib.parse.urlsplit(value)
    host=(p.hostname or '').lower()
    path=p.path.rstrip('/')
    m=re.fullmatch(r'/@[^/]+/post/([^/?#]+)', path)
    if host in {'threads.com','www.threads.com','threads.net','www.threads.net'} and m:
        canonical='https://www.threads.com'+path
        object_id=m.group(1)
except Exception:
    pass
print(canonical)
print(object_id)
PY
)
CANONICAL="${IDENTITY[0]:-}"
OBJECT_ID="${IDENTITY[1]:-}"
if [ -n "$CANONICAL" ] && [ -n "$OBJECT_ID" ]; then
  CANONICAL_STATE=resolved
else
  CANONICAL=''
  OBJECT_ID=''
  CANONICAL_STATE=pending
fi

esc() { printf "%s" "$1" | sed "s/'/''/g"; }
INPUT_SQL=$(esc "$INPUT")
CANON_SQL=$(esc "$CANONICAL")
OBJECT_SQL=$(esc "$OBJECT_ID")

# Keep the first canonical row for a Threads post object. A later share URL or
# tracking variant is retained as an input alias rather than becoming another
# monitored source. If an older pending input row exists, preserve its
# ingestion history before merging it into the canonical keeper.
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation >/dev/null <<SQL
INSERT INTO monitored_sources(id, source_type, input_url, canonical_url, source_object_id, status, sync_policy, last_seen_item_count, metadata)
VALUES (gen_random_uuid(), 'threads_public_post', 'https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh', 'https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh', 'DcWVvpwGTSh', 'active', 'active-6h', 33, '{"backfilled":true}'::jsonb)
ON CONFLICT (source_type, source_object_id) WHERE source_object_id IS NOT NULL DO UPDATE
SET status='active',
    sync_policy='active-6h',
    last_seen_item_count=GREATEST(monitored_sources.last_seen_item_count,33),
    updated_at=now();

DO \$\$
DECLARE
  v_input text := '$INPUT_SQL';
  v_canonical text := NULLIF('$CANON_SQL','');
  v_object text := NULLIF('$OBJECT_SQL','');
  v_state text := '$CANONICAL_STATE';
  keeper uuid;
  input_row uuid;
  input_seen integer := 0;
  input_sync timestamptz;
  input_meta jsonb := '{}'::jsonb;
  aliases jsonb;
BEGIN
  IF v_object IS NOT NULL THEN
    SELECT id INTO keeper
      FROM monitored_sources
     WHERE source_type='threads_public_post' AND source_object_id=v_object
     ORDER BY created_at,id LIMIT 1;

    SELECT id, last_seen_item_count, last_synced_at, metadata
      INTO input_row, input_seen, input_sync, input_meta
      FROM monitored_sources
     WHERE source_type='threads_public_post' AND input_url=v_input
     ORDER BY created_at,id LIMIT 1;

    IF keeper IS NULL THEN
      IF input_row IS NULL THEN
        INSERT INTO monitored_sources(
          id, source_type, input_url, canonical_url, source_object_id,
          status, sync_policy, metadata
        ) VALUES (
          gen_random_uuid(), 'threads_public_post', v_input, v_canonical, v_object,
          'active', 'active-6h', jsonb_build_object(
            'canonical_state',v_state,'input_aliases',jsonb_build_array(v_input)
          )
        ) RETURNING id INTO keeper;
      ELSE
        keeper := input_row;
        UPDATE monitored_sources
           SET canonical_url=v_canonical,
               source_object_id=v_object,
               status='active', sync_policy='active-6h',
               metadata=metadata || jsonb_build_object('canonical_state',v_state),
               updated_at=now()
         WHERE id=keeper;
      END IF;
    ELSIF input_row IS NOT NULL AND input_row <> keeper THEN
      UPDATE ingestion_runs SET source_id=keeper WHERE source_id=input_row;
      UPDATE monitored_sources k
         SET last_seen_item_count=GREATEST(k.last_seen_item_count,input_seen),
             last_synced_at=CASE
               WHEN k.last_synced_at IS NULL THEN input_sync
               WHEN input_sync IS NULL THEN k.last_synced_at
               ELSE GREATEST(k.last_synced_at,input_sync)
             END,
             metadata=k.metadata || input_meta,
             updated_at=now()
       WHERE k.id=keeper;
      DELETE FROM monitored_sources WHERE id=input_row;
    END IF;

    SELECT COALESCE(jsonb_agg(alias ORDER BY alias),'[]'::jsonb)
      INTO aliases
      FROM (
        SELECT DISTINCT value AS alias
          FROM jsonb_array_elements_text(
            COALESCE((SELECT metadata->'input_aliases' FROM monitored_sources WHERE id=keeper),'[]'::jsonb)
            || jsonb_build_array(v_input)
          )
      ) q;

    UPDATE monitored_sources
       SET canonical_url=v_canonical,
           source_object_id=v_object,
           status='active', sync_policy='active-6h',
           metadata=metadata || jsonb_build_object(
             'canonical_state',v_state,
             'input_aliases',aliases
           ),
           updated_at=now()
     WHERE id=keeper;
  ELSE
    INSERT INTO monitored_sources(
      id, source_type, input_url, canonical_url, source_object_id,
      status, sync_policy, metadata
    ) VALUES (
      gen_random_uuid(), 'threads_public_post', v_input, NULL, NULL,
      'active', 'active-6h', jsonb_build_object('canonical_state',v_state)
    )
    ON CONFLICT (source_type,input_url) DO UPDATE
      SET status='active', sync_policy='active-6h',
          metadata=monitored_sources.metadata || EXCLUDED.metadata,
          updated_at=now();
  END IF;
END \$\$;
SQL

# Re-run the invariant migration idempotently so every registration ends in a
# normalized, semantically deduplicated registry even after legacy pending rows.
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/006_threads_source_identity.sql >/dev/null

TOTAL=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(*) from monitored_sources where status='active';" | tr -d '\r')
INPUT_ESC=$(esc "$INPUT")
REGISTERED=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(*) from monitored_sources where source_type='threads_public_post' and status='active' and (input_url='$INPUT_ESC' or coalesce(metadata->'input_aliases','[]'::jsonb) ? '$INPUT_ESC');" | tr -d '\r')
UNIQUE_OBJECTS=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(distinct source_object_id) from monitored_sources where source_type='threads_public_post' and status='active' and source_object_id is not null;" | tr -d '\r')

printf '{"schema":"milkcat.vendor-source-register/v2","service_sha":"%s","active_sources":%s,"registered_input_alias":%s,"unique_source_objects":%s,"canonical_state":"%s","core_modified":false,"raw_threads_content_emitted":false}\n' "$SHA" "$TOTAL" "$REGISTERED" "$UNIQUE_OBJECTS" "$CANONICAL_STATE"
