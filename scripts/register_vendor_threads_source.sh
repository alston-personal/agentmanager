#!/usr/bin/env bash
set -euo pipefail

SHA="$1"
INPUT="$2"
DIR=/home/ubuntu/vendor-reputation-service
cd "$DIR"

git fetch --depth=1 origin "$SHA" >/dev/null 2>&1
git checkout --detach "$SHA" >/dev/null 2>&1

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation < sql/002_source_registry.sql >/dev/null

FINAL=$(curl -LsS --max-time 30 -o /dev/null -w '%{url_effective}' "$INPUT" || true)
if printf '%s' "$FINAL" | grep -Eq '^https://(www\.)?threads\.(com|net)/@[^/]+/post/[^/?#]+'; then
  CANONICAL="$FINAL"
  CANONICAL_STATE=resolved
else
  CANONICAL=''
  CANONICAL_STATE=pending
fi

esc() { printf "%s" "$1" | sed "s/'/''/g"; }
INPUT_SQL=$(esc "$INPUT")
CANON_SQL=$(esc "$CANONICAL")

docker compose exec -T db psql -v ON_ERROR_STOP=1 -U vendor_service -d vendor_reputation >/dev/null <<SQL
INSERT INTO monitored_sources(id, source_type, input_url, canonical_url, source_object_id, status, sync_policy, last_seen_item_count, metadata)
VALUES (gen_random_uuid(), 'threads_public_post', 'https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh', 'https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh', 'DcWVvpwGTSh', 'active', 'active-6h', 33, '{"backfilled":true}'::jsonb)
ON CONFLICT (source_type, input_url) DO UPDATE SET status='active', sync_policy='active-6h', last_seen_item_count=GREATEST(monitored_sources.last_seen_item_count,33), updated_at=now();

INSERT INTO monitored_sources(id, source_type, input_url, canonical_url, status, sync_policy, metadata)
VALUES (gen_random_uuid(), 'threads_public_post', '$INPUT_SQL', NULLIF('$CANON_SQL',''), 'active', 'active-6h', jsonb_build_object('canonical_state','$CANONICAL_STATE'))
ON CONFLICT (source_type, input_url) DO UPDATE SET canonical_url=COALESCE(EXCLUDED.canonical_url, monitored_sources.canonical_url), status='active', sync_policy='active-6h', metadata=monitored_sources.metadata || EXCLUDED.metadata, updated_at=now();
SQL

TOTAL=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(*) from monitored_sources where status='active';" | tr -d '\r')
NEW_COUNT=$(docker compose exec -T db psql -At -U vendor_service -d vendor_reputation -c "select count(*) from monitored_sources where source_type='threads_public_post' and input_url='$(esc "$INPUT")' and status='active';" | tr -d '\r')

printf '{"schema":"milkcat.vendor-source-register/v1","service_sha":"%s","active_sources":%s,"new_source_registered":%s,"canonical_state":"%s","core_modified":false,"raw_threads_content_emitted":false}\n' "$SHA" "$TOTAL" "$NEW_COUNT" "$CANONICAL_STATE"
