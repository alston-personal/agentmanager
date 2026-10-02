#!/usr/bin/env bash
set -euo pipefail

SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:?AGENTOS_SOURCE_COMMIT is required}"
ACCOUNT_REF="${AGENTOS_CONTENT_SOCIAL_ACCOUNT_REF:?AGENTOS_CONTENT_SOCIAL_ACCOUNT_REF is required}"
REPO="${AGENTOS_REPO:-/home/ubuntu/agentmanager}"
RELAY_ROOT="${AGENTOS_ACTION_RELAY_ROOT:-/home/ubuntu/agent-data/runtime/action-relay}"

printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'
printf '%s' "$ACCOUNT_REF" | grep -Eq '^[A-Za-z0-9._-]{1,80}$'

run_body() {
  cd "$REPO"
  export SOURCE_COMMIT ACCOUNT_REF RELAY_ROOT PYTHONPATH="$REPO"

  python3 - <<'PY'
import os,time
from agentos_node.runtime_converge_action_relay import ActionRelayRuntimeConvergeDispatcher

sha=os.environ["SOURCE_COMMIT"]
d=ActionRelayRuntimeConvergeDispatcher(os.environ["RELAY_ROOT"])
req={
    "schema":"agentos.runtime-converge-request/v1",
    "request_id":"content-social-"+sha[:20],
    "node_id":"oracle-core-node",
    "repository":"alston-personal/agentmanager",
    "source_ref":"core/integration",
    "source_commit":sha,
}
s=d.submit(request=req)
deadline=time.time()+360
print("content_social_converge_task="+s["task_id"])
while time.time()<deadline:
    r=d.inspect(s["task_id"])
    if r is not None:
        assert r.get("ok") is True,r
        assert r.get("resulting_commit")==sha,r
        print("content_social_converge=PASS")
        break
    time.sleep(1)
else:
    raise SystemExit("content_social_converge_timeout")
PY

  echo "action_relay_reconcile_trigger=ubuntu-owned-timer"
  for i in $(seq 1 420); do
    if python3 - "$SOURCE_COMMIT" <<'PY'
import json,sys
from pathlib import Path
p=Path("/home/ubuntu/agent-data/runtime/action-relay/capabilities.json")
if not p.is_file():
    raise SystemExit(1)
try:
    x=json.loads(p.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)
required={"agentos.content.social.bootstrap","agentos.content.social.inspect"}
ok=x.get("source_commit")==sys.argv[1] and required.issubset(set(x.get("actions") or []))
raise SystemExit(0 if ok else 1)
PY
    then
      echo "action_relay_generation=PASS"
      break
    fi
    sleep 1
    if [ "$i" -eq 420 ]; then
      echo "action_relay_generation=TIMEOUT" >&2
      exit 1
    fi
  done

  python3 - <<'PY'
import os,time
from agentos_node.content_publish_social_action_relay import ContentPublishSocialDispatcher

d=ContentPublishSocialDispatcher(os.environ["RELAY_ROOT"])
account=os.environ["ACCOUNT_REF"]

s=d.submit_bootstrap(account_ref=account)
deadline=time.time()+120
print("content_social_bootstrap_task="+s["task_id"])
while time.time()<deadline:
    r=d.inspect(s["task_id"])
    if r is not None:
        print("content_social_bootstrap_status="+str(r.get("status")))
        print("content_social_bootstrap_username="+str(r.get("username") or "unknown"))
        print("content_social_product_registration="+str(r.get("product_registration") or "unknown"))
        assert r.get("credential_exposed") is False,r
        assert r.get("public_publish_performed") is False,r
        assert r.get("credential_migrated") is True,r
        assert r.get("status")=="BOUND",r
        assert r.get("executor_user")=="ubuntu",r
        print("content_social_bootstrap=PASS")
        break
    time.sleep(1)
else:
    raise SystemExit("content_social_bootstrap_timeout")

s=d.submit_inspect(account_ref=account)
deadline=time.time()+120
print("content_social_inspect_task="+s["task_id"])
while time.time()<deadline:
    r=d.inspect(s["task_id"])
    if r is not None:
        print("content_social_inspect_status="+str(r.get("status")))
        print("content_social_username="+str(r.get("username") or "unknown"))
        print("content_social_write_entitlement="+str(r.get("write_entitlement")))
        assert r.get("credential_exposed") is False,r
        assert r.get("public_publish_performed") is False,r
        assert r.get("status")=="AUTHENTICATED",r
        assert r.get("executor_user")=="ubuntu",r
        print("content_social_account_inspect=PASS")
        break
    time.sleep(1)
else:
    raise SystemExit("content_social_inspect_timeout")
PY
}

if [ "$(id -un)" = "agentos-node" ]; then
  run_body
else
  export -f run_body
  sudo -n -u agentos-node env     SOURCE_COMMIT="$SOURCE_COMMIT"     ACCOUNT_REF="$ACCOUNT_REF"     RELAY_ROOT="$RELAY_ROOT"     REPO="$REPO"     bash -lc 'set -euo pipefail; cd "$REPO"; run_body'
fi

echo "content_social_reconcile=PASS"
