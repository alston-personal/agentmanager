#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPOSITORY="${AGENTOS_CONTROL_REPOSITORY:-alston-personal/agentmanager}"
ISSUE="${AGENTOS_CONTROL_ISSUE:-50}"
ENV_FILE="${AGENTOS_CONTROL_ENV:-/home/ubuntu/.config/agentos/control-inbox.env}"
UNIT="agentos-control-inbox.service"

validate_token() {
  local token="$1"
  [ -n "$token" ] || return 1
  local code
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
    -H 'Accept: application/vnd.github+json' \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    -H "Authorization: Bearer $token" \
    "https://api.github.com/repos/$REPOSITORY/issues/$ISSUE/comments?per_page=1") || return 1
  [ "$code" = 200 ]
}

TOKEN=''
SOURCE=''

if command -v gh >/dev/null 2>&1; then
  # Ignore inherited GH_TOKEN/GITHUB_TOKEN so gh tests its persistent ubuntu login.
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

[ -f "$ENV_FILE" ] || { echo "ERROR: control inbox env missing: $ENV_FILE" >&2; exit 21; }
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
awk '!/^AGENTOS_GITHUB_TOKEN=/' "$ENV_FILE" > "$TMP"
printf 'AGENTOS_GITHUB_TOKEN=%s\n' "$TOKEN" >> "$TMP"
install -m 0600 "$TMP" "$ENV_FILE"
unset TOKEN CANDIDATE CREDENTIAL

systemctl --user restart "$UNIT"
sleep 2
systemctl --user is-active --quiet "$UNIT"

# Prove the service credential itself can read the inbox without printing it.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
  -H 'Accept: application/vnd.github+json' \
  -H 'X-GitHub-Api-Version: 2022-11-28' \
  -H "Authorization: Bearer $AGENTOS_GITHUB_TOKEN" \
  "https://api.github.com/repos/$REPOSITORY/issues/$ISSUE/comments?per_page=1")
unset AGENTOS_GITHUB_TOKEN GH_TOKEN GITHUB_TOKEN
[ "$CODE" = 200 ] || { echo "ERROR: service credential validation returned HTTP $CODE" >&2; exit 22; }

echo "control_inbox_github_auth_repair=PASS"
echo "credential_source=$SOURCE"
echo "github_issue_read=PASS"
echo "control_inbox_service=active"
