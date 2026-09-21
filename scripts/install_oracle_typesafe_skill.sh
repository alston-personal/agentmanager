#!/usr/bin/env bash
# Oracle ubuntu-user installer: one TypeSafe installation method, scoped to the
# Antigravity IDE surface. Does NOT imply availability in agy/Claude/Codex.
# Deliberately not an AgentOS Control Inbox action or an Actions-triggered job.
set -euo pipefail
umask 077

if [[ "$(id -un)" != "ubuntu" || "$HOME" != "/home/ubuntu" ]]; then
  echo "ERROR: run in the Oracle ubuntu user session (without sudo)." >&2
  exit 2
fi
for command in node npx git sha256sum date; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "ERROR: missing prerequisite: $command" >&2
    exit 3
  fi
done

data_root="${AGENT_DATA_ROOT:-$HOME/agent-data}"
if [[ ! -d "$data_root" ]]; then
  echo "ERROR: expected existing AgentOS data root, not creating a second state store: $data_root" >&2
  exit 5
fi

# Official skills CLI route only; an explicit agent keeps this from installing
# accidentally into every IDE/CLI or silently broadening executor claims.
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --yes

skill_file="$HOME/.gemini/antigravity/skills/typesafe-ai/SKILL.md"
if [[ ! -s "$skill_file" ]] || ! grep -Fxq "name: typesafe-ai" "$skill_file"; then
  echo "ERROR: TypeSafe SKILL.md was not verified at $skill_file" >&2
  exit 4
fi

# The receipt records observed file bytes, NOT live session loading, model
# access, a new AgentOS capability, or other executor availability.
hash="$(sha256sum "$skill_file")"
hash="${hash%% *}"
installed_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
receipt_dir="$data_root/runtime/skills/typesafe-ai"
mkdir -p "$receipt_dir"
receipt_tmp="$(mktemp "$receipt_dir/install-receipt.json.XXXXXXXX")"
trap 'rm -f "$receipt_tmp"' EXIT
printf '{"schema":"agentos.skill-install-receipt/v1","skill":"typesafe-ai","agent":"antigravity","scope":"oracle-ubuntu-global","installation_method":"npx-skills-add","installed_at":"%s","skill_sha256":"%s","file_verified":true,"fresh_session_loaded":null,"agy_loaded":null}\n' \
  "$installed_at" "$hash" > "$receipt_tmp"
chmod 0600 "$receipt_tmp"
mv -f "$receipt_tmp" "$receipt_dir/install-receipt.json"
trap - EXIT

echo "TYPE_SAFE_SKILL=FILE_VERIFIED"
echo "AGENT=antigravity"
echo "SCOPE=oracle-ubuntu-global"
echo "SKILL_FILE=$skill_file"
echo "SKILL_SHA256=$hash"
echo "INSTALL_RECEIPT=$receipt_dir/install-receipt.json"
echo "SESSION_LOAD=UNVERIFIED"
echo "AGY_LOAD=UNVERIFIED"
