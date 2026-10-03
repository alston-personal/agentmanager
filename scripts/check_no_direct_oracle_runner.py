from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(".github/workflows")
DIRECT = re.compile(
    r"runs-on:\s*\[(?=[^\]]*self-hosted)(?=[^\]]*oracle)[^\]]*\]",
    re.IGNORECASE,
)
AUTOMATIC = re.compile(
    r"^\s{2}(push|pull_request|schedule|issues|issue_comment|repository_dispatch|workflow_run)\s*:",
    re.MULTILINE,
)


def trigger_block(text: str) -> str:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line == "on:"), None)
    if start is None:
        return ""
    out = [lines[start]]
    for line in lines[start + 1:]:
        if line and not line.startswith((" ", "\t")):
            break
        out.append(line)
    return "\n".join(out)


def changed_workflows() -> list[Path]:
    base_ref = os.environ.get("GITHUB_BASE_REF", "").strip()
    if not base_ref:
        return sorted(ROOT.glob("*.yml"))
    subprocess.run(
        ["git", "fetch", "--no-tags", "origin", base_ref],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD", "--", str(ROOT)],
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        Path(line.strip())
        for line in result.stdout.splitlines()
        if line.strip().endswith((".yml", ".yaml"))
    ]


violations: list[str] = []
manual_compat: list[str] = []
for path in changed_workflows():
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if not DIRECT.search(text):
        continue
    trigger = trigger_block(text)
    events = sorted(set(AUTOMATIC.findall(trigger)))
    if events:
        violations.append(f"{path}:automatic={','.join(events)}")
    else:
        manual_compat.append(str(path))

if manual_compat:
    print("direct_oracle_manual_compatibility="+str(len(manual_compat)))
    for item in manual_compat:
        print("manual_compatibility="+item)

if violations:
    print("direct_oracle_automatic_guard=FAIL")
    for item in violations:
        print("violation="+item)
    raise SystemExit(2)

print("direct_oracle_automatic_guard=PASS")
