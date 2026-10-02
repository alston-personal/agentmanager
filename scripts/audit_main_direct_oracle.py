from pathlib import Path
import re

ROOT=Path(".github/workflows")
pattern=re.compile(r"runs-on:\s*\[(?=[^\]]*self-hosted)(?=[^\]]*oracle)[^\]]*\]",re.I)

hits=[]
scheduled=[]
for p in sorted(ROOT.glob("*.yml")):
    text=p.read_text(encoding="utf-8",errors="replace")
    if not pattern.search(text):
        continue
    hits.append(str(p))
    head=text.split("\njobs:",1)[0]
    if re.search(r"^\s{2}schedule\s*:",head,re.M):
        scheduled.append(str(p))

print(f"direct_oracle_total={len(hits)}")
print(f"direct_oracle_scheduled={len(scheduled)}")
for p in hits:
    print("direct_oracle="+p)
for p in scheduled:
    print("scheduled_direct_oracle="+p)
