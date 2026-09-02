#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-future-safety-preflight.txt}
{
  echo "future_safety_preflight_begin"
  python3 - <<'PY'
import json,re
from pathlib import Path
root=Path('/home/ubuntu/metashield-protocol')
manifest=json.loads((root/'extension/manifest.json').read_text())
bg=(root/'extension/background.js').read_text(errors='replace')
api=(root/'api/server.js').read_text(errors='replace')
print('extension_version='+str(manifest.get('version')))
checks={
 'has_recovery_coverage_gate':'recoveryCoverageForOwnerKey' in bg,
 'has_recovery_required_code':'RECOVERY_COVERAGE_REQUIRED' in bg,
 'has_legacy_keyring':'legacyOwnerKeys' in bg and 'storeLegacyOwnerKey' in bg,
 'has_owner_key_lineage':'ownerKeyId' in bg or 'ownerKeyId' in api,
 'has_recovery_set_lineage':'recoverySetId' in bg or 'recoverySetId' in api,
 'has_recovery_coverage_lineage':'recoveryCoverage' in bg or 'recoveryCoverage' in api,
 'api_has_409':('409' in api and 'recoveryCoverage' in api),
}
for k,v in checks.items(): print(f'{k}={str(bool(v)).lower()}')
if not all(checks.values()): raise SystemExit('source invariant missing')
PY
  if [[ -f "$ROOT/scripts/test-no-irrecoverable-preservation.js" ]]; then
    echo "run_test_no_irrecoverable=1"
    node "$ROOT/scripts/test-no-irrecoverable-preservation.js"
  else
    echo "run_test_no_irrecoverable=0"
    echo "missing_test_no_irrecoverable"
    exit 2
  fi
  if [[ -f "$ROOT/scripts/test-threads-background.js" ]]; then
    echo "run_test_threads_background=1"
    node "$ROOT/scripts/test-threads-background.js"
  else
    echo "run_test_threads_background=0"
    echo "missing_test_threads_background"
    exit 3
  fi
  echo "future_safety_preflight=PASS"
} | tee "$OUT"
