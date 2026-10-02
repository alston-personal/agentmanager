#!/usr/bin/env bash
set -euo pipefail

UNIT_ROOT="${HOME}/.config/systemd/user"
FOUND=0
declare -A SEEN_PATH=()

for f in "${UNIT_ROOT}"/*.service "${UNIT_ROOT}"/*.timer; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  if printf '%s\n' "$name" | grep -Eiq 'persona.*pdca|pdca.*persona|mio.*pdca|pdca.*mio' ||      grep -Eiq 'persona.*pdca|pdca.*persona|persona_pdca|agentos-persona-pdca|persona_internal_activity_executor' "$f"; then
    FOUND=1
    echo "persona_pdca_runtime_unit=$name"
    while IFS= read -r line; do
      case "$line" in
        ExecStart=*|ExecStartPost=*|WorkingDirectory=*|OnCalendar=*|OnUnitActiveSec=*|OnBootSec=*|Unit=*)
          clean="${line//$HOME/%h}"
          echo "persona_pdca_runtime_directive=${name}:${clean}"
          case "$line" in
            ExecStart=*|ExecStartPost=*)
              cmd="${line#*=}"
              for token in $cmd; do
                token="${token#-}"
                token="${token#@}"
                case "$token" in
                  /*)
                    if [ -f "$token" ] && [ -z "${SEEN_PATH[$token]+x}" ]; then
                      SEEN_PATH["$token"]=1
                      rel="${token#$HOME/}"
                      digest="$(sha256sum "$token" | awk '{print $1}')"
                      echo "persona_pdca_runtime_file=${rel}"
                      echo "persona_pdca_runtime_sha256=${rel}:${digest}"
                    fi
                    ;;
                esac
              done
              ;;
          esac
          ;;
      esac
    done < "$f"
  fi
done

echo "persona_pdca_runtime_units_found=$FOUND"
echo "persona_pdca_runtime_probe=PASS"
