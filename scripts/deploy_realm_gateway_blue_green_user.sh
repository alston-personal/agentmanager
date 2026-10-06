#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
BG_REL="scripts/deploy_dashboard_blue_green_user.sh"
BG_EXACT="/tmp/agentos-dashboard-bg-$SOURCE_COMMIT.sh"
LOCAL='http://127.0.0.1:8780/v1/health'
PUBLIC='https://studio.milkcat.org/dashboard/api/agentos/v1/health'
CORE_RUNTIME_RELS=("agent_core/controller_service.py" "agent_core/controller_api.py" "agent_core/realm_server.py")

[[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 2
git -C "$REPO" cat-file -e "$SOURCE_COMMIT^{commit}"
git -C "$REPO" show "$SOURCE_COMMIT:$BG_REL" > "$BG_EXACT"
chmod 700 "$BG_EXACT"

BG_RUN_ID="$(date +%s)$$"
"$BG_EXACT" "$SOURCE_COMMIT" "$BG_RUN_ID" 1
echo "realm_gateway_dashboard_bg=PASS"

ACTIVE_SLOT="$(cat /home/ubuntu/agent-data/runtime/dashboard-blue-green/active-slot)"
ACTIVE_PORT="$(cat /home/ubuntu/agent-data/runtime/dashboard-blue-green/active-port)"
case "$ACTIVE_SLOT:$ACTIVE_PORT" in blue:3040|green:3041) ;; *) exit 3 ;; esac
echo "realm_gateway_dashboard_slot=$ACTIVE_SLOT"
echo "realm_gateway_dashboard_port=$ACTIVE_PORT"

TMP="$(mktemp -d)"
CORE_STAGE="$TMP/core-runtime"
CORE_BACKUP="$TMP/core-runtime-backup"
cleanup(){ rm -rf "$TMP"; rm -f "$BG_EXACT"; }
trap cleanup EXIT

mkdir -p "$CORE_STAGE" "$CORE_BACKUP"
for rel in "${CORE_RUNTIME_RELS[@]}"; do
  mkdir -p "$CORE_STAGE/$(dirname "$rel")" "$CORE_BACKUP/$(dirname "$rel")"
  git -C "$REPO" show "$SOURCE_COMMIT:$rel" > "$CORE_STAGE/$rel"
  cp "$REPO/$rel" "$CORE_BACKUP/$rel"
done
python3 -m py_compile   "$CORE_STAGE/agent_core/controller_service.py"   "$CORE_STAGE/agent_core/controller_api.py"   "$CORE_STAGE/agent_core/realm_server.py"
echo "realm_core_runtime_staged=PASS"

for rel in "${CORE_RUNTIME_RELS[@]}"; do cp "$CORE_STAGE/$rel" "$REPO/$rel"; done
echo "realm_core_runtime_cutover=PASS"

rollback_core(){
  set +e
  for rel in "${CORE_RUNTIME_RELS[@]}"; do cp "$CORE_BACKUP/$rel" "$REPO/$rel"; done
  systemctl --user restart agentos-realm-fabric.service || true
  set -e
}

if ! systemctl --user restart agentos-realm-fabric.service; then
  rollback_core
  exit 8
fi

ready=0
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "$LOCAL" >/tmp/agentos-realm-bg-health.json 2>/dev/null      && grep -q 'agentos.one-health/v0.1' /tmp/agentos-realm-bg-health.json      && grep -q 'realm-alston' /tmp/agentos-realm-bg-health.json; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" != 1 ]; then rollback_core; exit 9; fi
echo "realm_core_runtime_restart=PASS"
echo "realm_core_runtime_source_commit=$SOURCE_COMMIT"

public_ok=0
for _ in $(seq 1 20); do
  BODY="$(curl -fsS --max-time 5 "$PUBLIC" 2>/dev/null || true)"
  if printf '%s' "$BODY" | grep -q 'agentos.one-health/v0.1' && printf '%s' "$BODY" | grep -q 'realm-alston'; then
    public_ok=1
    break
  fi
  sleep 0.5
done
test "$public_ok" = 1
echo "realm_gateway_public=PASS"

for path in 'bootstrap?node_id=__gateway_probe__' 'dispatch'; do
  BODY_FILE="/tmp/realm-bg-route"
  code="$(curl -sS -o "$BODY_FILE" -w '%{http_code}' --max-time 8 "https://studio.milkcat.org/dashboard/api/agentos/v1/$path" || true)"
  test "$code" = 401
  ! grep -q 'Realm gateway route not allowlisted' "$BODY_FILE"
done

echo "realm_gateway_bootstrap_public=PASS"
echo "realm_gateway_dispatch_public=PASS"
echo "realm_gateway_source_commit=$SOURCE_COMMIT"
echo "realm_gateway_blue_green=PASS"
echo "nginx_mutation=BLUE_GREEN_HELPER"
echo "root_privilege=NGINX_RELOAD_ONLY"
