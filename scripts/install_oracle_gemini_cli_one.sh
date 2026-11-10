#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$(id -un)" != "ubuntu" || "$HOME" != "/home/ubuntu" ]]; then
  echo "ERROR: run as Oracle ubuntu user" >&2
  exit 2
fi

for command in node npm npx python3 sha256sum date; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: missing prerequisite: $command" >&2; exit 3; }
done

data_root="${AGENT_DATA_ROOT:-$HOME/agent-data}"
test -d "$data_root" || { echo "ERROR: AgentOS data root missing" >&2; exit 4; }

gemini_bin="$(command -v gemini 2>/dev/null || true)"
if [ -z "$gemini_bin" ]; then
  npm_prefix="$HOME/.local/share/agentos/npm-global"
  local_bin="$HOME/.local/bin"
  mkdir -p "$npm_prefix" "$local_bin"
  npm install --prefix "$npm_prefix" -g @google/gemini-cli@latest
  test -x "$npm_prefix/bin/gemini"
  ln -sfn "$npm_prefix/bin/gemini" "$local_bin/gemini"
  gemini_bin="$local_bin/gemini"
fi

test -x "$gemini_bin"
gemini_version="$("$gemini_bin" --version 2>/dev/null | head -n 1 || true)"
test -n "$gemini_version"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
python3 "$repo_root/scripts/install_gemini_cli_one.py" --repo "$repo_root" --mode oracle-local > /tmp/agentos-gemini-cli-one-install.json

settings="$HOME/.gemini/settings.json"
test -s "$settings"
python3 - "$settings" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding="utf-8"))
assert isinstance(p.get("mcpServers"), dict)
assert "agentos-one" in p["mcpServers"]
assert isinstance(p.get("hooks"), dict)
assert p["hooks"].get("SessionStart")
s=json.dumps(p, sort_keys=True).casefold()
for forbidden in ("node_token","access_token","refresh_token","client_secret","password"):
    assert forbidden not in s, forbidden
PY

settings_sha="$(sha256sum "$settings" | awk '{print $1}')"
installed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
receipt_dir="$data_root/runtime/gemini-cli-one"
mkdir -p "$receipt_dir"
python3 - "$receipt_dir/install-receipt.json" "$installed_at" "$gemini_version" "$settings_sha" <<'PY'
import json, os, sys
from pathlib import Path
path=Path(sys.argv[1])
payload={
  "schema":"agentos.gemini-cli-one-install-receipt/v1",
  "installed_at":sys.argv[2],
  "gemini_cli_version":sys.argv[3][:128],
  "settings_sha256":sys.argv[4],
  "cli_installed":True,
  "one_mcp_configured":True,
  "session_start_hook_configured":True,
  "auth_ready":None,
  "live_sessionstart_verified":None,
  "credential_exposed":False,
}
tmp=path.with_suffix(".tmp")
tmp.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
os.chmod(tmp,0o600)
tmp.replace(path)
PY

echo "GEMINI_CLI_ONE_INSTALL=PASS"
echo "GEMINI_CLI_AUTH=UNVERIFIED"
echo "GEMINI_CLI_SESSIONSTART=UNVERIFIED"
