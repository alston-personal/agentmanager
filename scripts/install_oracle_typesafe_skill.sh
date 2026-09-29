#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$(id -un)" != "ubuntu" || "$HOME" != "/home/ubuntu" ]]; then
  echo "ERROR: run as Oracle ubuntu user" >&2
  exit 2
fi

for command in node npx git sha256sum date; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: missing prerequisite: $command" >&2; exit 3; }
done

data_root="${AGENT_DATA_ROOT:-$HOME/agent-data}"
test -d "$data_root" || { echo "ERROR: AgentOS data root missing: $data_root" >&2; exit 4; }

npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --yes

skill_file="$HOME/.gemini/antigravity/skills/typesafe-ai/SKILL.md"
test -s "$skill_file"
grep -Fxq "name: typesafe-ai" "$skill_file"

hash="$(sha256sum "$skill_file" | awk '{print $1}')"
installed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
receipt_dir="$data_root/runtime/skills/typesafe-ai"
mkdir -p "$receipt_dir"
python3 - "$receipt_dir/install-receipt.json" "$installed_at" "$hash" <<'PY'
import json, os, sys
from pathlib import Path
path = Path(sys.argv[1])
payload = {
    "schema": "agentos.skill-install-receipt/v1",
    "skill": "typesafe-ai",
    "agent": "antigravity",
    "scope": "oracle-ubuntu-global",
    "installation_method": "npx-skills-add",
    "installed_at": sys.argv[2],
    "skill_sha256": sys.argv[3],
    "file_verified": True,
    "fresh_session_loaded": None,
    "agy_loaded": None,
    "credential_exposed": False,
}
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
tmp.replace(path)
PY

echo "TYPE_SAFE_SKILL=FILE_VERIFIED"
echo "TYPE_SAFE_SKILL_SHA256=$hash"
echo "TYPE_SAFE_SKILL_RECEIPT=$receipt_dir/install-receipt.json"
echo "TYPE_SAFE_SESSION_LOAD=UNVERIFIED"
echo "TYPE_SAFE_AGY_LOAD=UNVERIFIED"
