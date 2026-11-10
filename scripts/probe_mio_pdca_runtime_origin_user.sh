#!/usr/bin/env bash
set -euo pipefail

UNIT_ROOT="${HOME}/.config/systemd/user"
HEARTBEAT="${HOME}/.local/bin/agentos-persona-pdca-heartbeat"

# Emit bounded structural facts first so they survive the public receipt evidence cap.
# Never expose heartbeat source; only report whether the installed producer appears
# persona-generic or contains legacy Mio/sunlake identifiers.
if [ -f "$HEARTBEAT" ]; then
  echo "persona_pdca_heartbeat_present=1"
  echo "persona_pdca_heartbeat_sha256=$(sha256sum "$HEARTBEAT" | awk '{print $1}')"
  if grep -Eq 'AGENTOS_PERSONA_|persona_agent_registry|agent\.yaml|PERSONA_SLUG' "$HEARTBEAT"; then
    echo "persona_pdca_heartbeat_generic_markers=1"
  else
    echo "persona_pdca_heartbeat_generic_markers=0"
  fi
  if grep -Eiq 'sunlake|mio\.milkcat|sunlake-milkcat' "$HEARTBEAT"; then
    echo "persona_pdca_heartbeat_legacy_mio_markers=1"
  else
    echo "persona_pdca_heartbeat_legacy_mio_markers=0"
  fi
  if grep -Eiq 'oursong|oursong_alstonhuang|oursong-alstonhuang' "$HEARTBEAT"; then
    echo "persona_pdca_heartbeat_oursong_markers=1"
  else
    echo "persona_pdca_heartbeat_oursong_markers=0"
  fi
  if grep -Eiq 'my-agent-data|agent-data/personas|personas/' "$HEARTBEAT"; then
    echo "persona_pdca_heartbeat_data_path_markers=1"
  else
    echo "persona_pdca_heartbeat_data_path_markers=0"
  fi
  strings "$HEARTBEAT" 2>/dev/null | grep -Eo '/home/ubuntu/[^[:space:]"'"']*personas[^[:space:]"'"']*|[^[:space:]"'"']*my-agent-data[^[:space:]"'"']*|[^[:space:]"'"']*agent-data/personas[^[:space:]"'"']*' | sed 's#^/home/ubuntu/#%h/#' | sort -u | head -n 8 | sed 's/^/persona_pdca_heartbeat_path_hint=/' || true
else
  echo "persona_pdca_heartbeat_present=0"
  echo "persona_pdca_heartbeat_generic_markers=0"
  echo "persona_pdca_heartbeat_legacy_mio_markers=0"
  echo "persona_pdca_heartbeat_oursong_markers=0"
  echo "persona_pdca_heartbeat_data_path_markers=0"
fi
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
