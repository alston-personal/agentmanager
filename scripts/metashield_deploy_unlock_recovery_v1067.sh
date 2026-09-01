#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
python3 /tmp/metashield_fix_unlock_recovery_v1067.py "$ROOT"
cd "$ROOT/web-feed"
npm run build
PM2_CLI=$(find /home/ubuntu/.npm/_npx -path '*/node_modules/pm2/lib/binaries/CLI.js' -type f 2>/dev/null | head -n1)
test -n "$PM2_CLI"
PM2_HOME=/home/ubuntu/.pm2 node "$PM2_CLI" restart metashield-reborn
sleep 2
python3 - <<'PY'
import json, urllib.request
root='/home/ubuntu/metashield-protocol'
manifest=json.load(open(root+'/extension/manifest.json'))
page=open(root+'/web-feed/app/[wallet_address]/[platform]/page.tsx').read()
assert manifest['version']=='1.0.67'
for q in ['decryptPostDataWithOwnerRecovery','isOwnerRecoveryDecryptError(error)','await restoreWithLocalAAndVaultB()','return true;']:
    assert q in page, q
html=urllib.request.urlopen('https://studio.milkcat.org/echo/sunlake/all',timeout=20).read().decode('utf-8','replace')
assert '@sunlake' in html
assert '/echo//' not in html
print('manifest_version=1.0.67')
print('unlock_recovery_contract=PASS')
print('public_echo_route=PASS')
PY
git -C "$ROOT" status --short --branch
