#!/usr/bin/env bash
set -euo pipefail

REPO_SLUG="${AGENTOS_REPOSITORY:-alston-personal/agentmanager}"
REPO_URL="https://github.com/${REPO_SLUG}"
BASE="/home/agentos-node"
SOURCE="${AGENTOS_RUNNER_SOURCE:-$BASE/runner}"
POOL_ROOT="${AGENTOS_RUNNER_POOL_ROOT:-$BASE/runners}"

if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: invoke as deployment user, not root" >&2
  exit 2
fi
test -x "$SOURCE/config.sh"
test -x "$SOURCE/svc.sh"
sudo -n true

token=""
if command -v gh >/dev/null 2>&1; then
  token="$(gh auth token 2>/dev/null || true)"
fi
if [ -z "$token" ]; then
  cred="$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null || true)"
  token="$(printf '%s\n' "$cred" | sed -n 's/^password=//p' | head -n 1)"
  unset cred
fi
if [ -z "$token" ]; then
  echo "role_runner_pool=BLOCKED"
  echo "role_runner_pool_reason=github_registration_credential_unavailable"
  exit 20
fi

registration_token() {
  local tmp code
  tmp="$(mktemp)"
  code="$(curl -sS -o "$tmp" -w '%{http_code}' -X POST \
    -H "Authorization: Bearer $token" \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/$REPO_SLUG/actions/runners/registration-token" || true)"
  if [ "$code" != "201" ]; then
    echo "role_runner_registration_http=$code" >&2
    rm -f "$tmp"
    return 1
  fi
  python3 -c "import json,sys; d=json.load(open(sys.argv[1])); t=d.get('token'); assert t; print(t)" "$tmp"
  rm -f "$tmp"
}

copy_distribution() {
  local dest="$1"
  sudo -n mkdir -p "$dest"
  # Copy only immutable runner distribution bytes; never clone another runner's
  # identity, credentials, worktree or diagnostics.
  sudo -n bash -c "cd '$SOURCE' && tar \
    --exclude='./.runner' \
    --exclude='./.credentials' \
    --exclude='./.credentials_rsaparams' \
    --exclude='./_work' \
    --exclude='./_diag' \
    --exclude='./runner-recovery.log' \
    -cf - . | tar -C '$dest' -xf -"
  sudo -n chown -R agentos-node:agentos-node "$dest"
}

install_role() {
  local name="$1" labels="$2" cpu_quota="$3" mem_high="$4" mem_max="$5"
  local dest="$POOL_ROOT/$name"
  copy_distribution "$dest"

  if [ ! -s "$dest/.runner" ]; then
    local reg
    reg="$(registration_token)" || {
      echo "role_runner_$name=REGISTRATION_TOKEN_FAILED"
      return 1
    }
    sudo -n -u agentos-node env HOME=/home/agentos-node bash -c \
      "cd '$dest' && ./config.sh --unattended --replace --url '$REPO_URL' --token '$reg' --name '$name' --labels '$labels' --work '_work'"
    unset reg
  fi

  local unit
  unit="$(systemctl list-unit-files 'actions.runner.*.service' --no-legend 2>/dev/null | awk '{print $1}' | grep -F ".$name.service" | head -n 1 || true)"
  if [ -z "$unit" ]; then
    (cd "$dest" && sudo -n ./svc.sh install agentos-node)
    unit="$(systemctl list-unit-files 'actions.runner.*.service' --no-legend 2>/dev/null | awk '{print $1}' | grep -F ".$name.service" | head -n 1 || true)"
  fi
  test -n "$unit"

  local dropin="/etc/systemd/system/$unit.d"
  sudo -n mkdir -p "$dropin"
  printf '[Service]\nCPUAccounting=true\nMemoryAccounting=true\nCPUQuota=%s\nMemoryHigh=%s\nMemoryMax=%s\nOOMScoreAdjust=250\n' \
    "$cpu_quota" "$mem_high" "$mem_max" | sudo -n tee "$dropin/agentos-runner-pool.conf" >/dev/null
  sudo -n systemctl daemon-reload
  sudo -n systemctl enable --now "$unit" >/dev/null
  sudo -n systemctl is-active --quiet "$unit"
  echo "role_runner=$name labels=$labels unit=$unit cpu_quota=$cpu_quota memory_high=$mem_high memory_max=$mem_max state=active"
}

sudo -n mkdir -p "$POOL_ROOT"
sudo -n chown agentos-node:agentos-node "$POOL_ROOT"

# Capacity policy for the current 4-vCPU / ~24-GB Oracle VM:
# - GUI gets latency preference, but remains memory bounded.
# - Social API reads are parallel but deliberately cheap.
# - Control is exclusive at workflow/scheduler level and bounded here too.
install_role oracle-control  "oracle,control"          "100%" "2G" "4G"
install_role oracle-social-1 "oracle,social,social-1" "75%"  "1G" "2G"
install_role oracle-social-2 "oracle,social,social-2" "75%"  "1G" "2G"
install_role oracle-gui      "oracle,gui"              "125%" "2G" "3G"

unset token

active=0
for name in oracle-control oracle-social-1 oracle-social-2 oracle-gui; do
  unit="$(systemctl list-unit-files 'actions.runner.*.service' --no-legend 2>/dev/null | awk '{print $1}' | grep -F ".$name.service" | head -n 1 || true)"
  if [ -n "$unit" ] && systemctl is-active --quiet "$unit"; then
    active=$((active+1))
  fi
done

echo "role_runner_pool_active=$active"
test "$active" -eq 4
echo "role_runner_pool=PASS"
