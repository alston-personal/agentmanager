#!/usr/bin/env bash
set -euo pipefail

EXPECTED_USER="ubuntu"
REPO="alston-personal/ziwei-master"
DESCRIPTION="Deterministic Zi Wei Dou Shu chart engine, reusable rule library, renderer, and interpretation adapter"

actual_user="$(id -un)"
echo "executor_user=${actual_user}"
if [ "$actual_user" != "$EXPECTED_USER" ]; then
  echo "error=must run as ubuntu" >&2
  exit 2
fi

command -v gh >/dev/null

# GitHub Actions injects GITHUB_TOKEN/GH_TOKEN into the runner environment.
# Those variables override the ubuntu user's persistent gh authentication and
# can have narrower scopes than the canonical ubuntu GitHub identity. Remove
# only these ephemeral overrides; do not read, print, copy, or mutate the
# ubuntu credential store.
unset GITHUB_TOKEN GH_TOKEN

gh auth status

if gh repo view "$REPO" >/tmp/ziwei-master-view.txt 2>&1; then
  visibility="$(gh repo view "$REPO" --json visibility -q .visibility)"
  test "$visibility" = "PRIVATE"
  echo "repo=$REPO"
  echo "classification=ALREADY_EXISTS_PRIVATE"
  echo "idempotent=true"
  exit 0
fi

gh repo create "$REPO" --private --description "$DESCRIPTION"

visibility="$(gh repo view "$REPO" --json visibility -q .visibility)"
url="$(gh repo view "$REPO" --json url -q .url)"
test "$visibility" = "PRIVATE"

echo "repo=$REPO"
echo "url=$url"
echo "classification=CREATED_PRIVATE"
echo "idempotent=true"
