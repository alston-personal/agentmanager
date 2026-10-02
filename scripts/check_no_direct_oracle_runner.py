from __future__ import annotations

import re
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

violations = []
for path in sorted(ROOT.glob("*.yml")):
    text = path.read_text(encoding="utf-8", errors="replace")
    if pattern.search(text) and path.name not in ALLOW:
        violations.append(str(path))

if violations:
    print("direct_oracle_self_hosted_guard=FAIL")
    for item in violations:
        print("violation=" + item)
    raise SystemExit(2)

print("direct_oracle_self_hosted_guard=PASS")
