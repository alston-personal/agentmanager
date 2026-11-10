#!/usr/bin/env bash
# Shared Event Facility: one independent scheduler carrier for all registered personas.
# Never executes subscriber-provided code or directly performs any social write.
set -euo pipefail
[ "$(id -u)" = "1001" ] || { echo "agentos_event_facility_runtime=WRONG_USER" >&2; exit 2; }
ENGINE="${AGENTOS_EVENT_FACILITY:-$HOME/.local/lib/agentos/agentos_event_facility.py}"
LOCK=/tmp/agentos-persona-pdca-heartbeat.lock
test -f "$ENGINE"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "agentos_event_facility_runtime=BUSY"
  exit 0
fi
command -v gh >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth status >/dev/null
env -u GH_TOKEN -u GITHUB_TOKEN gh auth setup-git >/dev/null
DATA_REPO="$(mktemp -d /tmp/agentos-event-facility-XXXXXX)"
trap 'rm -rf "$DATA_REPO"' EXIT
env -u GH_TOKEN -u GITHUB_TOKEN gh repo clone alston-personal/my-agent-data "$DATA_REPO" -- --branch main --single-branch >/dev/null
git -C "$DATA_REPO" config --unset-all credential.helper || true
git -C "$DATA_REPO" config credential.https://github.com.helper '!/usr/bin/gh auth git-credential'
SHOULD_WAKE_MIO=0
EMITTED=0
SUBSCRIBERS=0
shopt -s nullglob
for subscription in "$DATA_REPO"/personas/*/pdca/event_subscriptions/*.json; do
  persona_dir="$(dirname "$(dirname "$subscription")")"
  slug="$(basename "$persona_dir")"
  [[ "$slug" =~ ^[a-z0-9-]+$ ]] || { echo "agentos_event_subscription=INVALID_SLUG" >&2; continue; }
  name="$(basename "$subscription" .json)"
  SUBSCRIBERS=$((SUBSCRIBERS+1))
  receipt="$persona_dir/pdca/event_receipts/$name-$(date -u +%Y%m%d).json"
  if result="$(python3 "$ENGINE" --persona-dir "$persona_dir" --subscription "pdca/event_subscriptions/$(basename "$subscription")" --receipt-out "$receipt")"; then
    count="$(python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("due_emitted",0)))' <<<"$result")"
    EMITTED=$((EMITTED+count))
    if [ "$count" -gt 0 ]; then
      cp "$receipt" "$persona_dir/pdca/event_receipts/$(date -u +%Y%m%dT%H%M%SZ)-$name-emission.json"
      # Persona-specific wake route is an allowlist of existing systemd services.
      # The subscriber's target string NEVER becomes a shell command/unit.
      immediate="$(python3 - "$subscription" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as stream:
    contract=json.load(stream)
print(int(contract.get("delivery",{}).get("mode")=="immediate"))
PY
)"
      if [ "$immediate" = "1" ]; then
        if [ "$slug" = "sunlake-milkcat" ]; then
          SHOULD_WAKE_MIO=1
        else
          echo "agentos_event_delivery=UNROUTABLE subscriber=$slug" >&2
        fi
      fi
    fi
  else
    echo "agentos_event_subscription=INVALID_OR_FAILED subscriber=$slug name=$name" >&2
  fi
done
shopt -u nullglob

# Recover events persisted before an unavailable service or a failed wake.
# Consumption is acknowledged by the Persona's last_event_timestamp cursor.
if python3 - "$DATA_REPO/personas/sunlake-milkcat" <<'PY'
import json,sys
from pathlib import Path
from datetime import datetime,timezone
root=Path(sys.argv[1])
try:
    state=json.loads((root/"pdca/state.json").read_text(encoding="utf-8"))
    lines=(root/"events/events.jsonl").read_text(encoding="utf-8").splitlines()[-300:]
except (OSError,ValueError):
    raise SystemExit(1)
def parse(value):
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (ValueError,TypeError): return datetime.min.replace(tzinfo=timezone.utc)
since=parse(state.get("last_event_timestamp"))
now=datetime.now(timezone.utc)
for line in lines:
    try: event=json.loads(line)
    except (ValueError,TypeError): continue
    if (event.get("source")=="agentos.event_facility"
        and event.get("target")=="persona:sunlake-milkcat"
        and event.get("delivery_policy")=="immediate"
        and since<parse(event.get("timestamp"))<=now):
        raise SystemExit(0)
raise SystemExit(1)
PY
then
  SHOULD_WAKE_MIO=1
fi

cd "$DATA_REPO"
git config user.name 'agentos-event-facility[bot]'
git config user.email 'agentos-event-facility@users.noreply.github.com'
git add -A -- personas
if ! git diff --cached --quiet; then
  git commit -m "event(facility): persist subscribed event draw and delivery intents" >/dev/null
  env -u GH_TOKEN -u GITHUB_TOKEN git -c 'credential.helper=!gh auth git-credential' push >/dev/null
fi
# Release the shared repository lock BEFORE requesting the existing Persona
# service, otherwise its normal runner would block on this same lock.
flock -u 9
if [ "$SHOULD_WAKE_MIO" -eq 1 ]; then
  if systemctl --user start --no-block agentos-persona-pdca-heartbeat.service; then
    echo "agentos_event_delivery=WAKE_REQUESTED subscriber=sunlake-milkcat"
  else
    echo "agentos_event_delivery=WAKE_FAILED subscriber=sunlake-milkcat" >&2
  fi
fi
echo "agentos_event_facility_runtime=PASS subscriptions=$SUBSCRIBERS emitted=$EMITTED"
