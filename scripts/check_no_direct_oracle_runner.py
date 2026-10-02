from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(".github/workflows")
ALLOW = {
    "oracle-one-break-glass-repair.yml",
    "oracle-runner-recovery.yml",
}

pattern = re.compile(
    r"runs-on:\s*\[(?=[^\]]*self-hosted)(?=[^\]]*oracle)[^\]]*\]",
    re.IGNORECASE,
)


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


violations = []
for path in changed_workflows():
    if not path.exists() or path.name in ALLOW:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if pattern.search(text):
        violations.append(str(path))

if violations:
    print("direct_oracle_self_hosted_guard=FAIL")
    for item in violations:
        print("violation=" + item)
    raise SystemExit(2)

print("direct_oracle_self_hosted_guard=PASS")
