#!/usr/bin/env bash
set -u
ROOT=/home/ubuntu/metashield-protocol
API="$ROOT/api"
WEB="$ROOT/web-feed"
FAIL=0
pass(){ echo "PASS $1"; }
fail(){ echo "FAIL $1"; FAIL=$((FAIL+1)); }
run(){ name="$1"; shift; echo "===== $name ====="; if "$@"; then pass "$name"; else fail "$name"; fi; }

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "branch=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
echo "head=$(git -C "$ROOT" rev-parse HEAD)"
echo "extension_version=$(python3 -c 'import json;print(json.load(open("'"$ROOT"'/extension/manifest.json"))["version"])')"
git -C "$ROOT" status --short --branch

echo '===== uploader source truth ====='
grep -nE '@irys/(sdk|upload|upload-ethereum)|Uploader|Ethereum' "$API/server.js" | sed -n '1,180p' || true
if grep -q '@irys/sdk' "$API/server.js"; then fail server_source_no_legacy_sdk; else pass server_source_no_legacy_sdk; fi
if grep -q '@irys/upload' "$API/server.js"; then pass server_source_current_upload; else fail server_source_current_upload; fi

echo '===== dependency readiness ====='
cd "$API" || exit 2
run api_npm_ci npm ci --omit=dev
run irys_upload_import node -e "Promise.all([import('@irys/upload'),import('@irys/upload-ethereum')]).then(()=>process.exit(0)).catch(e=>{console.error(e);process.exit(1)})"

echo '===== reload stale PM2 process ====='
ps -eo pid,lstart,args | grep '[n]ode /home/ubuntu/metashield-protocol/api/server.js' || true
if pm2 describe chamber-api >/tmp/chamber-api-before.txt 2>&1; then
  run chamber_api_restart pm2 restart chamber-api --update-env
  sleep 3
else
  fail chamber_api_present_in_pm2
fi
pm2 describe chamber-api | sed -n '1,100p' || true
ps -eo pid,lstart,args | grep '[n]ode /home/ubuntu/metashield-protocol/api/server.js' || true

run api_local_health curl -fsS --max-time 20 http://127.0.0.1:3011/chamber-api/health
run echo_local_root curl -fsS -L --max-time 20 http://127.0.0.1:3010/echo
run api_public_health curl -fsS --max-time 20 https://studio.milkcat.org/chamber-api/health
run echo_public_root curl -fsS -L --max-time 30 https://studio.milkcat.org/echo

echo '===== listeners / PM2 ====='
ss -ltnp | grep -E ':(3010|3011)\b' || true
pm2 status || true

echo '===== Irys devnet GraphQL ====='
if curl -fsS --max-time 20 -H 'content-type: application/json' --data '{"query":"query { transactions(first: 1, tags: [{name: \"App-Name\", values: [\"Chamber\"]}]) { edges { node { id } } } }"}' https://devnet.irys.xyz/graphql >/tmp/irys-graphql.json; then
  python3 -c "import json; d=json.load(open('/tmp/irys-graphql.json')); print('keys=', list(d.keys()))" || true
  pass irys_devnet_graphql
else
  fail irys_devnet_graphql
fi

echo '===== identity / timeline smoke ====='
if curl -fsS --max-time 20 http://127.0.0.1:3011/chamber-api/identity >/tmp/chamber-identities.json; then
  alias=$(python3 -c "import json; d=json.load(open('/tmp/chamber-identities.json')); print(next(iter((d.get('identities') or {}).keys()),''))" 2>/dev/null || true)
  echo "sample_alias=$alias"
  if test -n "$alias"; then
    run echo_sample_timeline curl -fsS -L --max-time 30 "https://studio.milkcat.org/echo/$alias/all"
  else
    fail sample_identity_available
  fi
else
  fail identity_api
fi

echo '===== selected deterministic tests ====='
cd "$ROOT" || exit 2
for f in scripts/test-i18n.js scripts/test-mvp-validation.js scripts/test-threads-platform.js scripts/test-instagram-platform.js scripts/test-threads-background.js scripts/test-recovery-vault.js scripts/test-secret-sharing.js; do
  if test -f "$f"; then
    echo "--- $f"
    if timeout 90 node "$f"; then pass "$f"; else fail "$f"; fi
  fi
done

echo '===== web-feed build ====='
if test -f "$WEB/package.json"; then
  cd "$WEB" || exit 2
  if timeout 240 npm run build; then pass web_feed_build; else fail web_feed_build; fi
else
  fail web_feed_package
fi

echo '===== recent runtime errors ====='
tail -n 40 "$ROOT/memory/dev-errors.ndjson" 2>/dev/null || true
echo '===== recent backup receipts ====='
tail -n 20 "$ROOT/memory/backup-receipts.ndjson" 2>/dev/null || true

echo "TOTAL_FAILURES=$FAIL"
if test "$FAIL" -eq 0; then echo 'FULL_REGRESSION=PASS'; else echo 'FULL_REGRESSION=FAIL'; fi
exit "$FAIL"
