#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$(id -un)" != "ubuntu" || "$HOME" != "/home/ubuntu" ]]; then
  echo "ERROR: run as Oracle ubuntu user" >&2
  exit 2
fi

data_root="${AGENT_DATA_ROOT:-$HOME/agent-data}"
test -d "$data_root" || { echo "ERROR: AgentOS data root missing: $data_root" >&2; exit 4; }
receipt_dir="$data_root/runtime/skills/typesafe-ai"
failure_file="$receipt_dir/install-failure.json"
mkdir -p "$receipt_dir"

write_failure() {
  local stage="$1" code="$2"
  printf '{"schema":"agentos.skill-install-failure/v1","skill":"typesafe-ai","stage":"%s","exit_code":%s,"credential_exposed":false}\n' "$stage" "$code" > "$failure_file.tmp"
  chmod 0600 "$failure_file.tmp"
  mv -f "$failure_file.tmp" "$failure_file"
}

for command in node npx git sha256sum date python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    write_failure "missing_$command" 3
    echo "ERROR: missing prerequisite: $command" >&2
    exit 3
  fi
done

npm_cache="$receipt_dir/npm-cache"
mkdir -p "$npm_cache"
chmod 0700 "$npm_cache"
export npm_config_cache="$npm_cache"

set +e
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --copy --yes
install_rc=$?
set -e
if [[ "$install_rc" -ne 0 ]]; then
  write_failure "npx_install" "$install_rc"
  echo "ERROR: TypeSafe skills CLI install failed" >&2
  exit "$install_rc"
fi

skill_file="$HOME/.gemini/antigravity/skills/typesafe-ai/SKILL.md"
if [[ ! -s "$skill_file" ]]; then
  write_failure "skill_file_missing" 5
  exit 5
fi
if ! grep -Fxq "name: typesafe-ai" "$skill_file"; then
  write_failure "skill_identity_mismatch" 6
  exit 6
fi

hash="$(sha256sum "$skill_file" | awk '{print $1}')"
installed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
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
rm -f "$failure_file"

echo "TYPE_SAFE_SKILL=FILE_VERIFIED"
echo "TYPE_SAFE_SKILL_SHA256=$hash"
echo "TYPE_SAFE_SKILL_RECEIPT=$receipt_dir/install-receipt.json"
echo "TYPE_SAFE_SESSION_LOAD=UNVERIFIED"
echo "TYPE_SAFE_AGY_LOAD=UNVERIFIED"
