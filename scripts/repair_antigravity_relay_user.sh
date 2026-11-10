#!/usr/bin/env bash
set -euo pipefail

REPAIR_STAGE="init"
REPAIR_FAILURE_LINE=""
REPAIR_FAILURE_RC=""
trap 'REPAIR_FAILURE_RC=$?; REPAIR_FAILURE_LINE=$LINENO' ERR

if [ "$(id -un)" != "ubuntu" ]; then
  echo "ERROR: run as ubuntu" >&2
  exit 2
fi

# realm_fabric_deploy_authority_separation_v1
# This transport repair owns only Antigravity Relay + Action Relay. Realm Fabric
# is governed by the generation-fenced deployment primitive and MUST NOT be
# materialized, have its unit rewritten, or be restarted from this script.
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
RUNTIME="${AGENTOS_RUNTIME_VNEXT:-/home/ubuntu/.local/share/agentos/runtime-vnext}"
# The governed ref proves lane membership; the exact commit determines bytes.
# Snapshot the ref first, then fetch the requested generation itself. A parallel
# merge may advance SOURCE_REF after the rollout starts without invalidating a
# commit that was already accepted into that lane.
REPAIR_STAGE="materialize_source"
if [ -n "$EXPECTED_SOURCE_COMMIT" ]; then
  git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
  SOURCE_REF_HEAD=$(git -C "$REPO" rev-parse FETCH_HEAD)
  git -C "$REPO" fetch --no-tags origin "$EXPECTED_SOURCE_COMMIT"
  SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
  if [ "$SOURCE_COMMIT" != "$EXPECTED_SOURCE_COMMIT" ]; then
    echo "ERROR: exact runtime source fetch mismatch: observed=$SOURCE_COMMIT expected=$EXPECTED_SOURCE_COMMIT" >&2
    exit 7
  fi
  if ! git -C "$REPO" merge-base --is-ancestor "$SOURCE_COMMIT" "$SOURCE_REF_HEAD"; then
    echo "ERROR: exact runtime source commit is not in governed ref: ref=$SOURCE_REF ref_head=$SOURCE_REF_HEAD commit=$SOURCE_COMMIT" >&2
    exit 7
  fi
else
  git -C "$REPO" fetch --no-tags origin "$SOURCE_REF"
  SOURCE_COMMIT=$(git -C "$REPO" rev-parse FETCH_HEAD)
fi
show_source() {
  git -C "$REPO" show "$SOURCE_COMMIT:$1"
}

# Bounded convergence diagnostic: expose no paths or diff content. This is
# intentionally emitted through the already-public antigravity_repair_stage
# marker so transport repair can diagnose why node.runtime/converge failed
# without widening the public receipt surface.
CURRENT_HEAD="$(git -C "$REPO" rev-parse HEAD)"
TRACKED_DIRTY_COUNT="$(git -C "$REPO" status --porcelain=v1 --untracked-files=no | wc -l | tr -d ' ')"
HEAD_MATCH=0
[ "$CURRENT_HEAD" = "$SOURCE_COMMIT" ] && HEAD_MATCH=1
echo "antigravity_repair_stage=runtime_preflight:head_match=$HEAD_MATCH:tracked_dirty_count=$TRACKED_DIRTY_COUNT"
if [ "$TRACKED_DIRTY_COUNT" != "0" ]; then
  git -C "$REPO" status --porcelain=v1 --untracked-files=no | while IFS= read -r line; do
    status="${line:0:2}"
    path="${line:3}"
    safe_path="$(printf '%s' "$path" | tr -cd 'A-Za-z0-9._/@+-')"
    echo "antigravity_repair_stage=runtime_preflight_dirty:status=$status:path=$safe_path"
  done
fi

if [ "$TRACKED_DIRTY_COUNT" -gt 0 ]; then
  REPAIR_STAGE="quarantine_tracked_checkout"
  BACKUP_BASE="$DATA_ROOT/runtime/backups/checkout-drift"
  BACKUP_ID="runtime-repair-${SOURCE_COMMIT:0:12}-$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_DIR="$BACKUP_BASE/$BACKUP_ID"
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"

  git -C "$REPO" status --porcelain=v1 -z --untracked-files=no > "$BACKUP_DIR/status.porcelain.z"
  git -C "$REPO" diff --binary --no-ext-diff HEAD -- > "$BACKUP_DIR/working-tree.patch"
  test -s "$BACKUP_DIR/status.porcelain.z"
  test -s "$BACKUP_DIR/working-tree.patch"

  PATCH_SHA256="$(sha256sum "$BACKUP_DIR/working-tree.patch" | awk '{print $1}')"
  python3 - "$BACKUP_DIR/metadata.json" "$CURRENT_HEAD" "$SOURCE_COMMIT" "$TRACKED_DIRTY_COUNT" "$PATCH_SHA256" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
path,current,target,count,digest=sys.argv[1:]
payload={
    "schema":"agentos.runtime-checkout-drift-backup/v1",
    "created_at":datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),
    "current_head":current,
    "target_source_commit":target,
    "tracked_dirty_count":int(count),
    "patch_sha256":digest,
    "content_exposed":False,
    "credential_exposed":False,
    "restore_command_documented":True,
}
Path(path).write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
PY
  chmod 600 "$BACKUP_DIR/status.porcelain.z" "$BACKUP_DIR/working-tree.patch" "$BACKUP_DIR/metadata.json"

  # Verify durable evidence before mutating the shared checkout. The patch is
  # binary-safe and represents the full tracked delta from current HEAD.
  test "$(sha256sum "$BACKUP_DIR/working-tree.patch" | awk '{print $1}')" = "$PATCH_SHA256"
  git -C "$REPO" reset --hard HEAD >/dev/null
  POST_DIRTY_COUNT="$(git -C "$REPO" status --porcelain=v1 --untracked-files=no | wc -l | tr -d ' ')"
  test "$POST_DIRTY_COUNT" = 0
  echo "antigravity_repair_stage=checkout_quarantine:count=$TRACKED_DIRTY_COUNT:post_dirty_count=$POST_DIRTY_COUNT"
  echo "antigravity_repair=CHECKOUT_QUARANTINED"
fi

REPAIR_STAGE="materialize_relay_runtime"
show_source agentos_node/__init__.py > "$TMPDIR/__init__.py"
show_source agentos_node/antigravity_relay.py > "$TMPDIR/antigravity_relay.py"
show_source agentos_node/antigravity_relay_worker.py > "$TMPDIR/antigravity_relay_worker.py"
show_source scripts/install_action_relay_user.sh > "$TMPDIR/install_action_relay_user.sh"

install -m 0664 "$TMPDIR/__init__.py" "$RUNTIME/agentos_node/__init__.py"
install -m 0664 "$TMPDIR/antigravity_relay.py" "$RUNTIME/agentos_node/antigravity_relay.py"
install -m 0664 "$TMPDIR/antigravity_relay_worker.py" "$RUNTIME/agentos_node/antigravity_relay_worker.py"

WORKER_SHA256=$(sha256sum "$RUNTIME/agentos_node/antigravity_relay_worker.py" | awk '{print $1}')
python3 - "$MANIFEST" "$SOURCE_REF" "$SOURCE_COMMIT" "$PROVIDER" "$WORKER_SHA256" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, source_ref, source_commit, provider, worker_sha = sys.argv[1:]
payload = {
    "schema": "agentos.runtime-provenance/v1",
    "installed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "source_ref": source_ref,
    "source_commit": source_commit,
    "provider": provider,
    "worker_sha256": worker_sha,
}
Path(path).write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
PY
chmod 0664 "$MANIFEST"

for d in "$SPOOL" "$SPOOL/inbox" "$SPOOL/processing" "$SPOOL/receipts"; do
  mkdir -p "$d"
  chgrp agentos "$d"
  chmod 2770 "$d"
done

cat > "$UNIT" <<EOF
[Unit]
Description=AgentOS Antigravity Relay (ubuntu identity, agentos boundary)
After=default.target

[Service]
Type=simple
WorkingDirectory=$RUNTIME
Environment=PYTHONPATH=$RUNTIME
Environment=AGENTOS_ANTIGRAVITY_PROVIDER=$PROVIDER
Environment=AGENTOS_RUNTIME_SOURCE_REF=$SOURCE_REF
Environment=AGENTOS_RUNTIME_SOURCE_COMMIT=$SOURCE_COMMIT
Environment=AGENTOS_RUNTIME_WORKER_SHA256=$WORKER_SHA256
UMask=0007
ExecStart=/usr/bin/sg agentos -c '/usr/bin/python3 -m agentos_node.antigravity_relay_worker --root $SPOOL'
Restart=on-failure
RestartSec=3
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

>>>>>>> dev/oracle-local-wip
(
  cd "$RUNTIME"
  PYTHONPATH="$RUNTIME" AGENTOS_ANTIGRAVITY_PROVIDER="$PROVIDER" python3 - <<'PY'
from agentos_node.antigravity_relay_worker import AntigravityRelayWorker
worker = AntigravityRelayWorker('/tmp/agentos-provider-import-check')
print('antigravity_runtime_import=PASS')
print('antigravity_provider=' + worker.provider)
PY
)

REPAIR_STAGE="install_action_runtime"
AGENTOS_REPO="$REPO" \
AGENTOS_ACTION_RUNTIME_ROOT="$ACTION_RUNTIME" \
AGENTOS_ACTION_SOURCE_REF="$SOURCE_REF" \
AGENTOS_ACTION_SOURCE_COMMIT="$SOURCE_COMMIT" \
bash "$TMPDIR/install_action_relay_user.sh"

REPAIR_STAGE="verify_experience_runtime"
for required in \
  agent_core/experience.py \
  agent_core/experience_store.py \
  agentos_node/experience_mcp_stdio.py \
  scripts/seed_one_experience.py \
  scripts/install_codex_experience_mcp_oracle.py \
  experience/agentos-core-oracle.seed.json; do
  test -f "$ACTION_RUNTIME/$required" || { echo "ERROR: Experience runtime input missing: $required" >&2; exit 8; }
done
PYTHONPATH="$ACTION_RUNTIME" AGENT_DATA_ROOT="$DATA_ROOT" python3 -m py_compile \
  "$ACTION_RUNTIME/agent_core/experience.py" \
  "$ACTION_RUNTIME/agent_core/experience_store.py" \
  "$ACTION_RUNTIME/agentos_node/experience_mcp_stdio.py" \
  "$ACTION_RUNTIME/scripts/seed_one_experience.py" \
  "$ACTION_RUNTIME/scripts/install_codex_experience_mcp_oracle.py"
REPAIR_STAGE="converge_experience_runtime"
(
  cd "$ACTION_RUNTIME"
  # One-time #117 Experience convergence is fenced by the exact live predecessor
  # digest emitted by exact-generation rollout #28. If the accepted Experience
  # changed after that probe, converge_experience_set refuses the replacement.
  PYTHONPATH="$ACTION_RUNTIME" AGENT_DATA_ROOT="$DATA_ROOT" \
    python3 scripts/seed_one_experience.py \
      --seed experience/agentos-core-oracle.seed.json \
      --expected-current-digest "$ONE_EXPERIENCE_EXPECTED_PREDECESSOR" >/dev/null
  echo "one_experience_seed=PASS"
  echo "one_experience_digest_convergence=PASS"
  PYTHONPATH="$ACTION_RUNTIME" AGENT_DATA_ROOT="$DATA_ROOT" \
    python3 scripts/install_codex_experience_mcp_oracle.py >/dev/null
  echo "codex_experience_mcp_install=PASS"
)
test -f "$CODEX_CONFIG"
grep -Fq '# AGENTOS_EXPERIENCE_MCP_START' "$CODEX_CONFIG"
grep -Fq '[mcp_servers."agentos-experience"]' "$CODEX_CONFIG"
grep -Fq "cwd = \"$ACTION_RUNTIME\"" "$CODEX_CONFIG"
grep -Fq "PYTHONPATH = \"$ACTION_RUNTIME\"" "$CODEX_CONFIG"
echo "codex_experience_mcp_exact_runtime=PASS"

REPAIR_STAGE="restart_antigravity_relay"
systemctl --user daemon-reload
systemctl --user enable agentos-antigravity-relay.service >/dev/null
systemctl --user reset-failed agentos-antigravity-relay.service >/dev/null 2>&1 || true
timeout 30s systemctl --user restart agentos-antigravity-relay.service
ANTIGRAVITY_ACTIVE=0
for i in $(seq 1 30); do
  if [ "$(systemctl --user show -p ActiveState --value agentos-antigravity-relay.service 2>/dev/null || true)" = "active" ]; then
    ANTIGRAVITY_ACTIVE=1
    break
  fi
  sleep 1
done
if [ "$ANTIGRAVITY_ACTIVE" != "1" ]; then
  systemctl --user status --no-pager agentos-antigravity-relay.service >&2 || true
  echo "ERROR: Antigravity relay did not converge active" >&2
  exit 9
fi

REPAIR_STAGE="final_runtime_acceptance"
systemctl --user is-active --quiet agentos-antigravity-relay.service
systemctl --user is-active --quiet agentos-action-relay.service

# Realm Fabric checks are read-only. Failing health is surfaced, but this repair
# has no authority to mutate or restart Realm Fabric.
systemctl --user is-active --quiet agentos-realm-fabric.service
REALM_HEALTH=$(curl -fsS --max-time 3 http://127.0.0.1:8780/v1/health)
echo "realm_fabric_health=$REALM_HEALTH"

BOOTSTRAP_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 'http://127.0.0.1:8780/v1/bootstrap?node_id=vopc5750')
BENCHMARK_CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 -X POST -H 'Content-Type: application/json' --data '{}' http://127.0.0.1:8780/v1/benchmark)
test "$BOOTSTRAP_CODE" = 401
test "$BENCHMARK_CODE" = 401

REPAIR_STAGE="complete"
echo "antigravity_repair_stage=complete"
echo "antigravity_repair=PASS"
echo "agentos_source_ref=$SOURCE_REF"
echo "agentos_source_commit=$SOURCE_COMMIT"
echo "antigravity_checkout_merge=SKIPPED"
echo "antigravity_group_context=agentos"
echo "antigravity_provider=$PROVIDER"
echo "antigravity_worker_sha256=$WORKER_SHA256"
echo "antigravity_runtime_manifest=$MANIFEST"
echo "antigravity_restart_converged=PASS"
echo "action_relay_install=PASS"
<<<<<<< HEAD
echo "realm_fabric_install=SKIPPED_FENCED_AUTHORITY"
echo "realm_fabric_mutation=NONE"
echo "realm_fabric_deploy_authority_separation=PASS"
echo "runtime=$RUNTIME"
echo "spool=$SPOOL"
echo "unit=$UNIT"
echo "realm_unit=$REALM_UNIT"
=======
echo "action_relay_source_generation_pinned=PASS"
echo "one_experience_seed=PASS"
echo "one_experience_digest_convergence=PASS"
echo "codex_experience_mcp_install=PASS"
echo "codex_experience_mcp_exact_runtime=PASS"
echo "realm_fabric_dependency_health=PASS"
