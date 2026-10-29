"""Read-only SHA-pinned branch convergence snapshot. Never infer runtime acceptance."""
import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "alston-personal/agentmanager"
TRACKED = ((1921, "governance"), (1923, "continuation-publisher"), (2029, "identity-audit"))

def remote_refs():
    result = subprocess.run(["git", "ls-remote", "--heads", "origin"], check=True,
                            capture_output=True, text=True, timeout=120)
    rows = {}
    for line in result.stdout.splitlines():
        sha, ref = line.split("\t", 1)
        if not ref.startswith("refs/heads/") or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha.lower()):
            raise ValueError("invalid branch ref")
        name = ref[len("refs/heads/"):]
        if name in rows:
            raise ValueError("duplicate branch name")
        rows[name] = sha
    if not {"main", "core/integration"}.issubset(rows):
        raise ValueError("missing mandatory branch refs")
    lines = "".join(f"{rows[name]}\trefs/heads/{name}\n" for name in sorted(rows))
    return rows, lines, hashlib.sha256(lines.encode()).hexdigest()

def classify_exact_tips(refs):
    """Exact commit identity only; never infer retirement or live use."""
    anchors = {"main": refs["main"], "core/integration": refs["core/integration"]}
    result = []
    for branch in sorted(refs):
        matches = [name for name, sha in anchors.items() if refs[branch] == sha]
        result.append({"branch": branch, "head_sha": refs[branch],
                       "exact_tip_matches": matches,
                       "content_disposition": "EXACT_TIP" if matches else "UNKNOWN",
                       "consumer_status": "UNKNOWN",
                       "retirement_allowed": False})
    return result

def shared_head_groups(refs):
    """Group exact commit-tip aliases; no patch equivalence or retirement inference."""
    by_sha = {}
    for name, sha in refs.items():
        by_sha.setdefault(sha, []).append(name)
    return [{"sha": sha, "branches": sorted(names), "size": len(names),
             "consumer_status": "UNKNOWN", "retirement_allowed": False}
            for sha, names in sorted(by_sha.items())
            if len(names) > 1]

def get_pr(number):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/pulls/{number}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "User-Agent": "agentos-convergence-progress"})
    with urllib.request.urlopen(req, timeout=20) as reply:
        return json.load(reply)

def main():
    refs, manifest, digest = remote_refs()
    Path("branch-heads.tsv").write_text(manifest, encoding="utf-8")
    classified = classify_exact_tips(refs)
    Path("branch-classification.json").write_text(
        json.dumps({"schema": "agentos.branch-exact-tip-triage/v1",
                    "manifest_sha256": digest,
                    "entries": classified}, indent=2) + "\n", encoding="utf-8")
    aliases = shared_head_groups(refs)
    Path("branch-shared-heads.json").write_text(
        json.dumps({"schema": "agentos.branch-shared-heads/v1",
                    "manifest_sha256": digest, "groups": aliases}, indent=2) + "\\n",
        encoding="utf-8")
    rows = []
    for number, capability in TRACKED:
        pr = get_pr(number)
        rows.append({"pr": number, "capability": capability, "url": pr["html_url"],
                     "head_sha": pr["head"]["sha"],
                     "code_state": "MERGED" if pr.get("merged_at") else ("DRAFT" if pr.get("draft") else pr["state"].upper()),
                     "runtime_acceptance": "UNKNOWN"})
    observed = datetime.now(timezone.utc).isoformat()
    payload = {"schema": "agentos.branch-convergence-progress/v2", "observed_at": observed,
               "branch_manifest": {"count": len(refs), "sha256": digest, "complete": True,
                                   "path": "branch-heads.tsv", "classification_path": "branch-classification.json",
                                   "shared_head_path": "branch-shared-heads.json",
                                   "shared_head_groups": len(aliases),
                                   "main_sha": refs["main"], "integration_sha": refs["core/integration"]},
               "tracked_prs": rows, "effective_capability_total": None,
               "runtime_accepted_count": None,
               "note": "Historical commits and branch count are not capability counts. Runtime requires independent receipts."}
    Path("progress.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = ["## Branch convergence — SHA-pinned source snapshot", "",
             f"UTC: {observed}", f"Remote branches: {len(refs)}",
             f"Manifest SHA256: `{digest}`", "",
             "| Capability | PR | Code state | Runtime |", "|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['capability']} | [#{row['pr']}]({row['url']}) | {row['code_state']} | UNKNOWN |")
    lines.extend(["", "Global convergence percentage: UNKNOWN; runtime acceptance not inferred.",
                  "No branch deletion, merging, deployment, or consumer-state inference."])
    report = "\n".join(lines) + "\n"
    Path("progress.md").write_text(report, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(report)
    print(report)

if __name__ == "__main__":
    main()
