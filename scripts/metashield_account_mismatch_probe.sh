#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-account-mismatch-probe.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
res={}
for rel in ['extension/background.js','web-feed/app/[wallet_address]/[platform]/page.tsx','api/recovery-vault.js']:
    p=root/rel
    s=p.read_text(errors='replace') if p.exists() else ''
    hits=[]
    for m in re.finditer(r'crypto\.accountMismatch|accountMismatch',s):
        line=s.count('\n',0,m.start())+1
        lo=max(0,m.start()-2200); hi=min(len(s),m.end()+3500)
        w=s[lo:hi]
        # only structural expressions / identifiers, no runtime values
        comps=sorted(set(re.findall(r'([A-Za-z_$][A-Za-z0-9_$.?]*\s*(?:===|!==|==|!=)\s*[A-Za-z_$][A-Za-z0-9_$.?]*)',w)))
        ids=sorted(set(re.findall(r'\b(accountId|setId|walletAddress|ownerAddress|decoded\.accountId|decoded\.setId|status\.accountId|status\.setId|payload\.accountId|payload\.setId)\b',w)))
        fn='<top-level>'
        prefix=s[:m.start()].splitlines()
        for ln in reversed(prefix[-180:]):
            mm=re.search(r'(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*async\s*\(|(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',ln)
            if mm:
                fn=mm.group(1) or mm.group(2); break
        hits.append({'line':line,'function':fn,'comparisons':comps[:40],'identifiers':ids})
    res[rel]={'hits':hits,'count':len(hits)}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
