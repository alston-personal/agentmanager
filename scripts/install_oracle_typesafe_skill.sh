#!/usr/bin/env bash
# Install the user-scoped TypeSafe agent skill on the Oracle Antigravity host.
# This is an explicit, human-authorized local installer, not a GitHub Actions
# trigger or a generic ONE/Control Inbox shell action.
set -euo pipefail

if [[ "$(id -un)" != "ubuntu" || "$HOME" != "/home/ubuntu" ]]; then
  echo "ERROR: run in the Oracle ubuntu user session (without sudo)." >&2
  exit 2
fi
for command in node npx git; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "ERROR: missing prerequisite: $command" >&2
    exit 3
  fi
done

# Exactly one vendor-supported installation route: the skills CLI, selecting
# the Antigravity agent. Global scope survives project checkout changes.
npx --yes skills add typesafe-ai/skills --skill typesafe-ai --agent antigravity --global --yes

skill_file="$HOME/.gemini/antigravity/skills/typesafe-ai/SKILL.md"
if [[ ! -s "$skill_file" ]] || ! grep -Fxq "name: typesafe-ai" "$skill_file"; then
  echo "ERROR: TypeSafe SKILL.md was not verified at $skill_file" >&2
  exit 4
fi

echo "TYPE_SAFE_SKILL=FILE_VERIFIED"
echo "AGENT=antigravity"
echo "SCOPE=oracle-ubuntu-global"
echo "SKILL_FILE=$skill_file"
echo "NOTE=Validate loading in a fresh Oracle Antigravity session separately."
