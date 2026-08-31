#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol

python3 /tmp/metashield_fix_no_irrecoverable_gate.py
node --check "$ROOT/extension/background.js"
node --check "$ROOT/extension/sidepanel.js"
node --check "$ROOT/extension/i18n.js"
node --check "$ROOT/api/server.js"
grep -q '"version": "1.0.64"' "$ROOT/extension/manifest.json"
grep -q 'RECOVERY_COVERAGE_REQUIRED' "$ROOT/extension/background.js"
grep -q 'RECOVERY_COVERAGE_REQUIRED' "$ROOT/extension/sidepanel.js"
grep -q 'Recovery coverage is required before preservation' "$ROOT/api/server.js"
grep -q 'recovery_set_id' "$ROOT/api/server.js"
grep -q 'recovery_coverage' "$ROOT/api/server.js"
grep -q 'owner_key_id' "$ROOT/api/server.js"

echo '===== deterministic tests ====='
cd "$ROOT"
test -f scripts/test-i18n.js && node scripts/test-i18n.js
test -f scripts/test-mvp-validation.js && node scripts/test-mvp-validation.js
if test -f scripts/test-threads-background.js; then
  if node scripts/test-threads-background.js; then
    echo 'threads_background=PASS'
  else
    echo 'threads_background=NEEDS_G9_FIXTURE'
  fi
fi

echo '===== restart current Chamber API ====='
PM2_HOME=/home/ubuntu/.pm2
export PM2_HOME
PM2_CLI=$(find /home/ubuntu/.npm/_npx -maxdepth 7 -type f -path '*/node_modules/pm2/lib/binaries/CLI.js' 2>/dev/null | sort | head -1)
test -n "$PM2_CLI"
node "$PM2_CLI" restart chamber-api --update-env
sleep 4
curl -fsS --max-time 20 http://127.0.0.1:3011/chamber-api/health
echo

echo '===== API G9 negative smoke ====='
code=$(curl -sS -o /tmp/g9-negative.json -w '%{http_code}' \
  -H 'content-type: application/json' \
  --data '{"content":"ciphertext","isEncrypted":true,"encryptionVersion":"post-key-v2","network":"devnet"}' \
  http://127.0.0.1:3011/chamber-api/backup)
cat /tmp/g9-negative.json
echo
test "$code" = "409"
python3 - <<'PY'
import json
d=json.load(open('/tmp/g9-negative.json'))
assert d.get('code') == 'RECOVERY_COVERAGE_REQUIRED', d
print('api_g9_negative=PASS')
PY

echo '===== source gate order ====='
python3 - <<'PY'
from pathlib import Path
s=Path('/home/ubuntu/metashield-protocol/extension/background.js').read_text()
gate=s.index('const recoveryCoverage = await recoveryCoverageForOwnerKey')
postkey=s.index('const postKeyBytes = crypto.getRandomValues', gate)
media=s.index('for (const [mediaIndex, url] of mediaUrls.entries())', gate)
assert gate < postkey < media
print('extension_gate_before_ciphertext_and_media=PASS')
PY

echo '===== diff ====='
git -C "$ROOT" diff -- extension/background.js extension/sidepanel.js extension/i18n.js extension/manifest.json api/server.js | sed -n '1,620p'
echo '===== worktree ====='
git -C "$ROOT" status --short --branch
