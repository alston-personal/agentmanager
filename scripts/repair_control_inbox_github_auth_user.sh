#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPOSITORY="${AGENTOS_CONTROL_REPOSITORY:-alston-personal/agentmanager}"
ISSUE="${AGENTOS_CONTROL_ISSUE:-50}"
ENV_FILE="${AGENTOS_CONTROL_ENV:-/home/ubuntu/.config/agentos/control-inbox.env}"
CONTROLLER_ENV="${AGENTOS_CONTROLLER_ENV:-/home/ubuntu/.config/agentos/controller.env}"
DATA_ROOT="${AGENT_DATA_ROOT:-/home/ubuntu/agent-data}"
UNIT="agentos-control-inbox.service"

valid_single_line_token() {
  local token="$1"
  [ -n "$token" ] || return 1
  case "$token" in
    *$'\n'*|*$'\r'*|*' '*|*$'\t'*) return 1 ;;
  esac
  # GitHub token families in current and legacy forms; keep this structural only.
  case "$token" in
    ghp_*|github_pat_*|gho_*|ghu_*|ghs_*|ghr_*|[A-Za-z0-9_]* ) ;;
    *) return 1 ;;
  esac
}

validate_token() {
  local token="$1"
  valid_single_line_token "$token" || return 1
  local code
  code=$(curl --http1.1 -sS -o /dev/null -w '%{http_code}' --max-time 10 \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    -H "Authorization: Bearer $token" \
    "https://api.github.com/repos/$REPOSITORY/issues/$ISSUE/comments?per_page=1") || return 1
  [ "$code" = 200 ]
}

TOKEN=''
SOURCE=''

if command -v gh >/dev/null 2>&1; then
  # Ignore inherited variables so gh tests the persistent ubuntu login.
  if env -u GH_TOKEN -u GITHUB_TOKEN gh api "repos/$REPOSITORY/issues/$ISSUE" --jq '.number' >/dev/null 2>&1; then
    CANDIDATE=$(env -u GH_TOKEN -u GITHUB_TOKEN gh auth token 2>/dev/null || true)
    if validate_token "$CANDIDATE"; then
      TOKEN="$CANDIDATE"
      SOURCE='gh-auth'
    fi
  fi
fi

if [ -z "$TOKEN" ]; then
  CREDENTIAL=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null || true)
  CANDIDATE=$(printf '%s\n' "$CREDENTIAL" | sed -n 's/^password=//p' | head -n 1)
  if validate_token "$CANDIDATE"; then
    TOKEN="$CANDIDATE"
    SOURCE='git-credential'
  fi
fi

if [ -z "$TOKEN" ]; then
  echo "ERROR: no valid ubuntu GitHub API credential for $REPOSITORY issue $ISSUE" >&2
  echo "Run: gh auth login --hostname github.com" >&2
  exit 20
fi

[ -f "$CONTROLLER_ENV" ] || { echo "ERROR: controller env missing: $CONTROLLER_ENV" >&2; exit 21; }
CONTROLLER_TOKEN=$(sed -n 's/^AGENTOS_CONTROLLER_TOKEN=//p' "$CONTROLLER_ENV" | head -n 1)
valid_single_line_token "$CONTROLLER_TOKEN" || { echo "ERROR: invalid controller token file" >&2; exit 22; }

# Rebuild the service env from a strict allowlist. Never preserve arbitrary or
# malformed lines from an older env file; a previously multi-line credential
# must not survive repair.
mkdir -p "$(dirname "$ENV_FILE")"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
umask 077
cat > "$TMP" <<EOF
AGENTOS_GITHUB_TOKEN=$TOKEN
AGENTOS_CONTROLLER_TOKEN=$CONTROLLER_TOKEN
AGENTOS_CONTROL_REPOSITORY=$REPOSITORY
AGENTOS_CONTROL_ISSUE=$ISSUE
AGENTOS_CONTROL_ALLOWED_LOGIN=alstonhuang
AGENTOS_ONE_URL=http://127.0.0.1:8780
AGENTOS_CONTROL_POLL_SECONDS=3
AGENTOS_CONTROL_RECEIPT_WAIT_SECONDS=45
AGENT_DATA_ROOT=$DATA_ROOT
EOF

# Exactly nine KEY=VALUE lines, no whitespace-bearing values.
[ "$(wc -l < "$TMP")" -eq 9 ] || { echo "ERROR: rebuilt env line count invalid" >&2; exit 23; }
if grep -nEv '^[A-Z0-9_]+=[^[:space:]]+$' "$TMP" >/dev/null; then
  echo "ERROR: rebuilt env contains malformed line" >&2
  exit 24
fi
install -m 0600 "$TMP" "$ENV_FILE"
unset TOKEN CANDIDATE CREDENTIAL CONTROLLER_TOKEN

systemctl --user restart "$UNIT"
sleep 2
systemctl --user is-active --quiet "$UNIT"

# Validate the credential from the rebuilt env without shell-sourcing it.
SERVICE_TOKEN=$(sed -n 's/^AGENTOS_GITHUB_TOKEN=//p' "$ENV_FILE" | head -n 1)
validate_token "$SERVICE_TOKEN" || { echo "ERROR: rebuilt service credential cannot read inbox" >&2; exit 25; }
unset SERVICE_TOKEN

echo "control_inbox_github_auth_repair=PASS"
echo "credential_source=$SOURCE"
echo "github_issue_read=PASS"
echo "control_inbox_env_rebuilt=PASS"
echo "control_inbox_service=active"
