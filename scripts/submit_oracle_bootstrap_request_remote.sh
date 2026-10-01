#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-}"
REQUEST_ID="${2:-}"
SOURCE_COMMIT="${3:-}"
EXTRA_PARAMS_JSON="${4-}"
if [ -z "$EXTRA_PARAMS_JSON" ]; then EXTRA_PARAMS_JSON='{}'; fi
TIMEOUT_SECONDS="${AGENTOS_RECEIPT_TIMEOUT_SECONDS:-600}"

: "${ORACLE_HOST:?ORACLE_HOST required}"
: "${DEPLOY_USER:?DEPLOY_USER required}"
DEPLOY_SSH_PORT="${DEPLOY_SSH_PORT:-22}"

printf '%s' "$ACTION" | grep -Eq '^agentos\.[A-Za-z0-9_.]+$'
printf '%s' "$REQUEST_ID" | grep -Eq '^[A-Za-z0-9._-]{1,140}$'
printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
printf '%s' "$TIMEOUT_SECONDS" | grep -Eq '^[0-9]{1,4}$'
python3 -c 'import json,sys; d=json.loads(sys.argv[1]); assert isinstance(d,dict)' "$EXTRA_PARAMS_JSON"

SSH_OPTS=(
  -o StrictHostKeyChecking=accept-new
  -o ConnectTimeout=8
  -o ServerAliveInterval=15
  -o ServerAliveCountMax=2
  -p "$DEPLOY_SSH_PORT"
)

EXTRA_PARAMS_B64="$(printf '%s' "$EXTRA_PARAMS_JSON" | base64 | tr -d '\n')"

# Submit in a short SSH session. The AgentOS scheduler owns execution after the
# request is atomically materialized, so a later network interruption cannot
# cancel or ambiguously re-run the governed action.
ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$ORACLE_HOST" \
  bash -s -- "$ACTION" "$REQUEST_ID" "$SOURCE_COMMIT" "$EXTRA_PARAMS_B64" <<'REMOTE' >&2
set -euo pipefail
ACTION="$1"
REQUEST_ID="$2"
SOURCE_COMMIT="$3"
EXTRA_PARAMS_JSON="$(printf '%s' "$4" | base64 -d)"
REPO=/home/ubuntu/agentmanager
ROOT=/tmp/agentos-bootstrap-control
REQUESTS="$ROOT/requests"
RECEIPTS="$ROOT/receipts"
REQUEST="$REQUESTS/$REQUEST_ID.request.json"
RECEIPT="$RECEIPTS/$REQUEST_ID.json"

mkdir -p "$REQUESTS" "$RECEIPTS" "$ROOT/locks"
chmod 1777 "$ROOT" "$REQUESTS" "$RECEIPTS"

(
  exec 9>"$ROOT/locks/oracle-source-materialize.lock"
  flock -w 60 9
  if ! git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}" 2>/dev/null; then
    git -C "$REPO" fetch --no-tags origin "$SOURCE_COMMIT" >/dev/null
  fi
)

# A prior terminal receipt for the same deterministic request ID is safe to
# reuse. Otherwise create exactly one request as agentos-node.
if [ -s "$RECEIPT" ]; then
  echo "request_already_completed=$REQUEST_ID"
  exit 0
fi

sudo -n -u agentos-node env \
  ACTION="$ACTION" REQUEST_ID="$REQUEST_ID" SOURCE_COMMIT="$SOURCE_COMMIT" EXTRA_PARAMS_JSON="$EXTRA_PARAMS_JSON" REQUEST="$REQUEST" \
  python3 - <<'PY'
import json,os
from datetime import datetime,timezone
from pathlib import Path
params=json.loads(os.environ['EXTRA_PARAMS_JSON'])
if not isinstance(params,dict):
    raise SystemExit('extra params must be object')
params={'source_commit':os.environ['SOURCE_COMMIT'],**params}
path=Path(os.environ['REQUEST'])
payload={
    'schema':'agentos.bootstrap-request/v1',
    'request_id':os.environ['REQUEST_ID'],
    'action':os.environ['ACTION'],
    'created_at':datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
    'params':params,
    'authority':{'source':'github-actions','target_user':'ubuntu','arbitrary_shell':False},
}
tmp=path.with_suffix(path.suffix+'.tmp')
tmp.write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n',encoding='utf-8')
os.chmod(tmp,0o644)
tmp.replace(path)
os.chmod(path,0o644)
PY
echo "request_submitted=$REQUEST_ID"
REMOTE

# Poll with short independent SSH sessions instead of keeping one connection
# idle for the full build/restart window. This turns transient SSH loss into a
# retryable observation failure rather than a false deployment failure.
deadline=$((SECONDS + TIMEOUT_SECONDS))
while [ "$SECONDS" -lt "$deadline" ]; do
  set +e
  RECEIPT_JSON="$(
    ssh "${SSH_OPTS[@]}" "$DEPLOY_USER@$ORACLE_HOST" \
      bash -s -- "$REQUEST_ID" <<'REMOTE'
set -euo pipefail
REQUEST_ID="$1"
RECEIPT="/tmp/agentos-bootstrap-control/receipts/$REQUEST_ID.json"
[ -s "$RECEIPT" ] || exit 4
cat "$RECEIPT"
REMOTE
  )"
  rc=$?
  set -e
  if [ "$rc" -eq 0 ] && [ -n "$RECEIPT_JSON" ]; then
    printf '%s\n' "$RECEIPT_JSON"
    exit 0
  fi
  sleep 4
done

echo "receipt timeout for $REQUEST_ID" >&2
exit 3
