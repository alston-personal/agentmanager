#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
python3 /tmp/metashield_fix_historical_recovery_v1068.py "$ROOT"
node --check "$ROOT/extension/background.js"
node "$ROOT/extension/tests/historical-recovery-contract.test.mjs"
if [ -f "$ROOT/extension/tests/passkey-recovery-bridge-contract.test.mjs" ]; then node "$ROOT/extension/tests/passkey-recovery-bridge-contract.test.mjs"; fi
if [ -f "$ROOT/scripts/test-threads-background.js" ]; then node "$ROOT/scripts/test-threads-background.js"; fi
python3 - <<'PY'
import json
p='/home/ubuntu/metashield-protocol/extension/manifest.json'
print('manifest_version='+json.load(open(p))['version'])
PY
grep -n "historicalRecovery" "$ROOT/extension/background.js"
grep -n "crypto.shareSetMismatch\|recoveryChecksum\|storeLegacyOwnerKey" "$ROOT/extension/background.js" | head -20
echo 'git_status_begin'
git -C "$ROOT" status --short --branch
echo 'git_status_end'
