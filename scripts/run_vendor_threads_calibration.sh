#!/usr/bin/env bash
set -uo pipefail

SHA="${1:?service sha required}"
BASE=/home/ubuntu/vendor-reputation-service
ERR=/tmp/vendor-threads-calibration.err
: >"$ERR"

emit_failure() {
  local stage="$1" rc="$2"
  python3 - "$stage" "$rc" "$ERR" <<'PY'
import json,pathlib,sys
stage,rc,path=sys.argv[1],int(sys.argv[2]),sys.argv[3]
p=pathlib.Path(path)
text=' '.join((p.read_text(errors='replace') if p.exists() else '').split())[-800:]
print(json.dumps({
  'schema':'milkcat.threads-vendor-signal-calibration/v1',
  'ok':False,
  'failed_stage':stage,
  'requests':0,
  'results_seen':0,
  'qualified_under_current_filter':0,
  'filtered_out':0,
  'filtered_hint_counts':{},
  'by_harvest_term':{},
  'errors':[{'exception_type':'carrier_failure','detail':text}],
  'raw_text_emitted':False,
  'raw_text_persisted':False,
  'candidate_db_modified':False,
  'reviews_published':False
},ensure_ascii=False))
PY
  exit "$rc"
}

if [ ! -d "$BASE/.git" ]; then echo 'service git repo missing' >"$ERR"; emit_failure repo 2; fi
git -C "$BASE" fetch --depth=1 origin "$SHA" >"$ERR" 2>&1 || emit_failure fetch $?
git -C "$BASE" checkout --detach "$SHA" >"$ERR" 2>&1 || emit_failure checkout $?

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
python3 scripts/calibrate_threads_vendor_signals.py 2>"$ERR" || emit_failure calibration $?
