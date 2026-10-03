from pathlib import Path
import re

ROOT=Path(".github/workflows")
rows=[]
for p in sorted(ROOT.glob("*.yml")):
    text=p.read_text(encoding="utf-8",errors="replace")
    head=text.split("\njobs:",1)[0]
    automatic=bool(re.search(r"^\s{2}(push|pull_request|schedule|issues|issue_comment|repository_dispatch|workflow_run)\s*:",head,re.M))
    if not automatic:
        continue
    markers=[]
    if "webfactory/ssh-agent" in text: markers.append("ssh-agent")
    if re.search(r"(^|\s)ssh\s+(?:\\\n\s*)?-",text): markers.append("ssh-cli")
    if "submit_oracle_bootstrap_request_remote.sh" in text: markers.append("remote-bootstrap-helper")
    if re.search(r"runs-on:\s*\[(?=[^\]]*self-hosted)[^\]]*\]",text,re.I): markers.append("direct-self-hosted")
    if markers:
        rows.append((str(p),markers))
print("automatic_runner_bypass_total="+str(len(rows)))
for p,m in rows:
    print("bypass="+p+":"+",".join(m))
