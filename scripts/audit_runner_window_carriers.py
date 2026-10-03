from pathlib import Path
import re

ROOT=Path(".github/workflows")
rows=[]
for p in sorted(ROOT.glob("*.yml")):
    text=p.read_text(encoding="utf-8",errors="replace")
    head=text.split("\njobs:",1)[0]
    events=re.findall(r"^\s{2}(push|pull_request|schedule|issues|issue_comment|repository_dispatch|workflow_run)\s*:",head,re.M)
    automatic=bool(events)
    if not automatic:
        continue
    markers=[]
    if "webfactory/ssh-agent" in text: markers.append("ssh-agent")
    if re.search(r"(^|\s)ssh\s+(?:\\\n\s*)?-",text): markers.append("ssh-cli")
    if "submit_oracle_bootstrap_request_remote.sh" in text: markers.append("remote-bootstrap-helper")
    if re.search(r"runs-on:\s*\[(?=[^\]]*self-hosted)[^\]]*\]",text,re.I): markers.append("direct-self-hosted")
    if markers:
        rows.append((str(p),sorted(set(events)),markers))
print("automatic_runner_bypass_total="+str(len(rows)))
print("scheduled_runner_bypass_total="+str(sum("schedule" in e for _,e,_ in rows)))
for p,e,m in rows:
    print("bypass="+p+":events="+",".join(e)+":markers="+",".join(m))
