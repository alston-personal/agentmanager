#!/usr/bin/env bash
set -euo pipefail

UNIT_ROOT="${HOME}/.config/systemd/user"
FOUND=0

for f in "${UNIT_ROOT}"/*.service "${UNIT_ROOT}"/*.timer; do
  [ -f "$f" ] || continue
  if grep -Eiq 'persona.*pdca|pdca.*persona|persona_pdca|agentos-persona-pdca' "$f"; then
    FOUND=1
    name="$(basename "$f")"
    echo "persona_pdca_runtime_unit=$name"
    while IFS= read -r line; do
      case "$line" in
        ExecStart=*|ExecStartPost=*|OnCalendar=*|OnUnitActiveSec=*|OnBootSec=*|Unit=*)
          clean="${line//$HOME/%h}"
          echo "persona_pdca_runtime_directive=${name}:${clean}"
          ;;
      esac
    done < "$f"
  fi
done

# Find local source files referenced by PDCA units or carrying the stable bot/runtime markers.
declare -A SEEN=()
for root in "${HOME}/agentmanager" "${HOME}/.local/share/agentos"; do
  [ -d "$root" ] || continue
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    rel="${f#$HOME/}"
    if [ -z "${SEEN[$f]+x}" ]; then
      SEEN["$f"]=1
      digest="$(sha256sum "$f" | awk '{print $1}')"
      echo "persona_pdca_runtime_file=${rel}"
      echo "persona_pdca_runtime_sha256=${rel}:${digest}"
    fi
  done < <(grep -RIlE --exclude='*.json' --exclude='*.jsonl' --exclude='*.log'     'persona_pdca_runtime|agentos-persona-pdca\[bot\]|persona_internal_activity_executor'     "$root" 2>/dev/null | head -n 24)
done

echo "persona_pdca_runtime_units_found=$FOUND"
echo "persona_pdca_runtime_probe=PASS"
