#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$(id -un)" != "ubuntu" || "$HOME" != "/home/ubuntu" ]]; then
  echo "ERROR: run as Oracle ubuntu user" >&2
  exit 2
fi

for command in node npm python3 date; do
  command -v "$command" >/dev/null 2>&1 || { echo "ERROR: missing prerequisite: $command" >&2; exit 3; }
done

data_root="${AGENT_DATA_ROOT:-$HOME/agent-data}"
test -d "$data_root" || { echo "ERROR: AgentOS data root missing" >&2; exit 4; }

npm_prefix="$HOME/.local/share/agentos/npm-global"
local_bin="$HOME/.local/bin"
mkdir -p "$npm_prefix" "$local_bin"

codex_bin="$(command -v codex 2>/dev/null || true)"
if [ -z "$codex_bin" ]; then
  npm install --prefix "$npm_prefix" -g @openai/codex@latest
  test -x "$npm_prefix/bin/codex"
  ln -sfn "$npm_prefix/bin/codex" "$local_bin/codex"
  codex_bin="$local_bin/codex"
fi

test -x "$codex_bin"
codex_version="$("$codex_bin" --version 2>/dev/null | head -n 1 || true)"
test -n "$codex_version"

installed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
receipt_dir="$data_root/runtime/codex-cli"
mkdir -p "$receipt_dir"
python3 - "$receipt_dir/install-receipt.json" "$installed_at" "$codex_version" "$codex_bin" <<'PY'
import json, os, sys
from pathlib import Path
path=Path(sys.argv[1])
payload={
  "schema":"agentos.codex-cli-install-receipt/v1",
  "installed_at":sys.argv[2],
  "codex_cli_version":sys.argv[3][:128],
  "executable_path":sys.argv[4],
  "cli_installed":True,
  "auth_ready":None,
  "credential_exposed":False,
}
tmp=path.with_suffix(".tmp")
tmp.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
os.chmod(tmp,0o600)
tmp.replace(path)
PY

echo "CODEX_CLI_INSTALL=PASS"
echo "CODEX_CLI_AUTH=UNVERIFIED"
