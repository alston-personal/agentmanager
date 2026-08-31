#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-web-bridge-scan.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); needles=['PREPARE_RECOVERY_VAULT','CONFIRM_RECOVERY_VAULT','FINALIZE_RECOVERY_VAULT','RESTORE_RECOVERY_VAULT','/recovery/passkey/','createNativePasskey','authenticateNativePasskey']
rows=[]
for base in [root/'extension',root/'web-feed']:
 if not base.exists(): continue
 for p in base.rglob('*'):
  if not p.is_file() or p.suffix.lower() not in ('.js','.jsx','.ts','.tsx','.html'): continue
  try:s=p.read_text(errors='replace')
  except:continue
  hits=[n for n in needles if n in s]
  if not hits: continue
  msgs=sorted(set(re.findall(r'["\']([A-Z][A-Z0-9_]{4,})["\']',s)))
  rows.append({'path':str(p.relative_to(root)),'hits':hits,'recoveryMessages':[m for m in msgs if any(k in m for k in ('RECOVER','RECOVERY','PASSKEY','VAULT','RESTORE','PREPARE','CONFIRM','FINALIZE'))][:120]})
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
