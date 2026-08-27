#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"
: "${RELEASE_ROOT:?RELEASE_ROOT is required}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"
BRANCH="feature/distributed-agentos-runtime"

REQUEST_LIST="${1:-/tmp/agentos_request_files}"
[ -s "$REQUEST_LIST" ] || exit 0
mkdir -p agentos-github-bus/responses

while IFS= read -r REQUEST_PATH; do
  [ -n "$REQUEST_PATH" ] || continue
  REQUEST_ID="$(basename "$REQUEST_PATH" .json)"
  RESPONSE_PATH="agentos-github-bus/responses/${REQUEST_ID}.json"

  RESPONSE="$(ssh -o StrictHostKeyChecking=accept-new -p "$DEPLOY_SSH_PORT" "${DEPLOY_USER}@${DEPLOY_HOST}" \
    bash -s -- "$RELEASE_ROOT" "$REQUEST_PATH" <<'REMOTE'
set -euo pipefail
RELEASE_ROOT="$1"
REQUEST_PATH="$2"
REF="feature/distributed-agentos-runtime"
git -C "$RELEASE_ROOT" fetch --prune origin "$REF" >/dev/null
git -C "$RELEASE_ROOT" checkout --detach "$(git -C "$RELEASE_ROOT" rev-parse FETCH_HEAD)" >/dev/null
set -a
[ -f "$HOME/agentmanager/.env" ] && source "$HOME/agentmanager/.env"
[ -f "$HOME/.agentos.secrets" ] && source "$HOME/.agentos.secrets"
[ -f "$HOME/.config/agentos/distributed.env" ] && source "$HOME/.config/agentos/distributed.env"
set +a
export AGENTOS_CONTROL_PLANE_URL="http://127.0.0.1:8765"
export AGENTOS_CONTROL_PLANE_TOKEN="${AGENTOS_CHATGPT_CLIENT_TOKEN:?missing scoped ChatGPT client token}"
PYTHON_BIN="${AGENTOS_DISTRIBUTED_PYTHON:-$(command -v python3)}"
set +e
PYTHONPATH="$RELEASE_ROOT" "$PYTHON_BIN" "$RELEASE_ROOT/scripts/process_chatgpt_github_request.py" "$RELEASE_ROOT/$REQUEST_PATH"
exit 0
REMOTE
  )"

  test -n "$RESPONSE"
  printf '%s\n' "$RESPONSE" > "$RESPONSE_PATH"
  python3 -m json.tool "$RESPONSE_PATH" >/dev/null
done < "$REQUEST_LIST"

git config user.name "agentos-command-bus"
git config user.email "agentos-command-bus@users.noreply.github.com"
git add agentos-github-bus/responses/
git diff --cached --quiet && exit 0
git commit -m "agentos(bus): respond to ChatGPT command"
for attempt in 1 2 3; do
  if git push origin "HEAD:$BRANCH"; then
    exit 0
  fi
  git pull --rebase origin "$BRANCH"
done
exit 1
