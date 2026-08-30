#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
HEAD = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
SELF = Path(__file__).resolve()

# Only changed repository automation/code needs to be checked. Existing legacy
# paths can be retired incrementally without making this guard impossible to
# introduce. Once merged, any newly-added bypass fails the PR.
proc = subprocess.run(
    ["git", "diff", "--name-only", f"{BASE}...{HEAD}"],
    check=True,
    capture_output=True,
    text=True,
)
changed = [Path(p) for p in proc.stdout.splitlines() if p.strip()]

patterns = [
    (re.compile(r"\bgit\s+push\b[^\n]*(?:\bmain\b|HEAD:main)"), "direct git push to main"),
    (re.compile(r"\bgh\s+api\b[^\n]*git/refs/heads/main"), "GitHub API main ref mutation"),
    (re.compile(r"refs/heads/main"), "explicit main ref mutation"),
]

violations: list[str] = []
for path in changed:
    if not path.exists() or path.is_dir():
        continue
    # The detector necessarily contains the forbidden tokens in its regexes;
    # do not classify its own source text as a publication bypass.
    if path.resolve() == SELF:
        continue
    if not (
        str(path).startswith(".github/workflows/")
        or str(path).startswith("scripts/")
        or str(path).startswith("agent_")
        or str(path).startswith("agentos_")
    ):
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for regex, label in patterns:
        for match in regex.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path}:{line}: {label}")

if violations:
    print("MAINLINE_GOVERNANCE=FAIL")
    for item in violations:
        print(item)
    print("Development mutations must use a non-main branch + PR + governed promotion.")
    raise SystemExit(1)

print("MAINLINE_GOVERNANCE=PASS")
