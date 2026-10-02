from pathlib import Path
import re

ROOT=Path(".github/workflows")
BASELINE=Path(".agentos/governance/main-legacy-direct-oracle-workflows.txt")
pattern=re.compile(r"runs-on:\s*\[(?=[^\]]*self-hosted)(?=[^\]]*oracle)[^\]]*\]",re.I)

legacy={x.strip() for x in BASELINE.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")}
current={str(p) for p in ROOT.glob("*.yml") if pattern.search(p.read_text(encoding="utf-8",errors="replace"))}
new=sorted(current-legacy)
scheduled=[]
for rel in sorted(current):
    text=Path(rel).read_text(encoding="utf-8",errors="replace")
    head=text.split("\njobs:",1)[0]
    if re.search(r"^\s{2}schedule\s*:",head,re.M):
        scheduled.append(rel)

print(f"main_direct_oracle_legacy={len(current & legacy)}")
print(f"main_direct_oracle_new={len(new)}")
print(f"main_direct_oracle_scheduled={len(scheduled)}")
for item in new:
    print("new_violation="+item)
for item in scheduled:
    print("scheduled_violation="+item)
if new or scheduled:
    raise SystemExit(2)
print("main_runner_window_guard=PASS")
