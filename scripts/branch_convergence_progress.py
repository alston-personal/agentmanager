"""Emit honest PR-gated convergence progress, never infer runtime acceptance."""
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "alston-personal/agentmanager"
TRACKED = ((1921, "governance"), (1923, "continuation-publisher"))

def get_pr(number):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/pulls/{number}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "User-Agent": "agentos-convergence-progress"})
    with urllib.request.urlopen(req, timeout=20) as reply:
        return json.load(reply)

def main():
    rows = []
    for number, lane in TRACKED:
        pr = get_pr(number)
        merged = bool(pr.get("merged_at"))
        rows.append({"pr": number, "lane": lane,
                     "stage": "MERGED" if merged else "DRAFT" if pr.get("draft") else "OPEN_REVIEW",
                     "merged": merged, "merged_at": pr.get("merged_at"),
                     "url": pr["html_url"], "head_sha": pr["head"]["sha"],
                     "runtime_accepted": False})
    snapshot = {"schema": "agentos.branch-convergence-progress/v1",
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "tracked_prs": rows, "merged_prs": sum(x["merged"] for x in rows),
                "runtime_accepted_count": 0,
                "runtime_count_note": "Not inferred from PR or CI; requires explicit receipt"}
    Path("progress.json").write_text(json.dumps(snapshot, indent=2))
    report = ["## Branch convergence — evidence-based PR progress",
              "", "> Historical ahead/behind is not progress. Unknown effective-capability denominator: no global percentage.",
              "", "| Lane | PR | Stage | Runtime accepted |", "|---|---|---|---|"]
    for x in rows:
        report.append(f"| {x['lane']} | [#{x['pr']}]({x['url']}) | {x['stage']} | not established |")
    report += ["", f"**Merged tracked PRs: {snapshot['merged_prs']} / {len(rows)}** (not all effective capability gaps)",
               "", "**Runtime accepted:** not established from these sources.",
               "", f"Observed UTC: {snapshot['observed_at']}",
               "", "Canonical work coordination: https://github.com/alston-personal/agentmanager/issues/1682"]
    summary = "\n".join(report)+"\n"
    Path("progress.md").write_text(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    print(summary)

if __name__ == "__main__":
    main()
