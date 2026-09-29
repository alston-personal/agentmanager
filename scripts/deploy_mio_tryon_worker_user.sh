#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_tryon_deploy=WRONG_USER" >&2
  exit 2
fi

REPO="/home/ubuntu/agentmanager"
MAIN_ENV="$REPO/.env"
ROOT="$HOME/.local/share/mio-tryon"
VENV="$HOME/.local/share/mio-tryon-venv"
BIN="$HOME/.local/bin"
CFG="$HOME/.config/agentos"
UNIT_DIR="$HOME/.config/systemd/user"
WORKER="$BIN/agentos-mio-tryon-render-worker.py"
ENV_FILE="$CFG/mio-tryon.env"
UNIT="$UNIT_DIR/agentos-mio-tryon-render-worker.service"

test -d "$REPO/.git"
test -f "$MAIN_ENV" || { echo "mio_tryon_deploy=HF_ENV_MISSING" >&2; exit 3; }

HF_TOKEN_VALUE="$(python3 - "$MAIN_ENV" <<'PY'
from pathlib import Path
import shlex,sys
p=Path(sys.argv[1])
value=""
for raw in p.read_text(encoding="utf-8").splitlines():
    line=raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k,v=line.split("=",1)
    if k.strip()=="HF_TOKEN":
        v=v.strip()
        if len(v)>=2 and v[0]==v[-1] and v[0] in "'\"":
            v=v[1:-1]
        value=v
print(value)
PY
)"
test -n "$HF_TOKEN_VALUE" || { echo "mio_tryon_deploy=HF_TOKEN_EMPTY" >&2; exit 3; }

mkdir -p "$ROOT" "$BIN" "$CFG" "$UNIT_DIR"

git -C "$REPO" fetch origin main >/dev/null
WORKER_COMMIT="$(git -C "$REPO" rev-parse origin/main)"
git -C "$REPO" show "$WORKER_COMMIT:scripts/tryon_render_worker.py" > "$WORKER.tmp"
install -m 755 "$WORKER.tmp" "$WORKER"
rm -f "$WORKER.tmp"

if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet --upgrade "gradio_client>=1.13,<3" "Pillow>=10,<13"
"$VENV/bin/python" -m py_compile "$WORKER"

umask 077
printf 'HF_TOKEN=%s\n' "$HF_TOKEN_VALUE" > "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset HF_TOKEN_VALUE

cat > "$UNIT" <<'UNIT'
[Unit]
Description=AgentOS Mio Outfit Try-On Render Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=HOME=/home/ubuntu
Environment=AGENT_DATA_ROOT=/home/ubuntu/agent-data
Environment=AGENTOS_TRYON_POLL_SECONDS=2
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/home/ubuntu/.config/agentos/mio-tryon.env
ExecStart=/home/ubuntu/.local/share/mio-tryon-venv/bin/python /home/ubuntu/.local/bin/agentos-mio-tryon-render-worker.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
systemctl --user daemon-reload
systemctl --user enable agentos-mio-tryon-render-worker.service >/dev/null
systemctl --user restart agentos-mio-tryon-render-worker.service
for i in $(seq 1 30); do
  systemctl --user is-active --quiet agentos-mio-tryon-render-worker.service && break
  sleep 1
done
systemctl --user is-active --quiet agentos-mio-tryon-render-worker.service

echo "mio_tryon_worker_source_commit=$WORKER_COMMIT"
echo "mio_any_item_hf_token_configured=yes"
echo "mio_tryon_worker_service=active"

ROOT_DATA="$HOME/agent-data/projects/dressup-simulator"
JOB_DIR="$ROOT_DATA/render_jobs/runtime"
ASSET_DIR="$ROOT_DATA/render_assets"
JOB_ID="mio-shoe-live-e2e-bootstrap-$(date +%s)"
JOB="$JOB_DIR/$JOB_ID.json"
ASSET="$ASSET_DIR/$JOB_ID.webp"
mkdir -p "$JOB_DIR" "$ASSET_DIR"
rm -f "$JOB" "$ASSET"

python3 - "$JOB" "$JOB_ID" <<'PY'
import json, pathlib, sys
from datetime import datetime, timezone
path=pathlib.Path(sys.argv[1]); job_id=sys.argv[2]
now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
job={
  "schema":"agentos.tryon-render-job/v1",
  "jobId":job_id,
  "characterId":"sunlake-milkcat-ai-001",
  "characterVersion":"mio-body-v1",
  "view":"front","pose":"neutral_standing","status":"queued",
  "requestedAt":now,"startedAt":None,"completedAt":None,"failedAt":None,"supersededBy":None,
  "input":{
    "baseBodyAsset":"/personas/mio/mio-avatar.webp",
    "layerOrder":["shoes"],
    "selectedLayers":{
      "shoes":{
        "garmentId":"net-40832-002",
        "name":"防潑水帆布鞋",
        "layer":"shoes",
        "sourceImageUrl":"https://m.net-fashion.net/product/735479"
      }
    }
  },
  "output":{"asset":None,"previewAsset":None,"width":None,"height":None},
  "error":None
}
path.write_text(json.dumps(job,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
path.chmod(0o600)
PY

OK=0
for i in $(seq 1 150); do
  STATE="$(python3 - "$JOB" <<'PY'
import json,sys
try:
    print(json.load(open(sys.argv[1],encoding='utf-8')).get('status','missing'))
except Exception:
    print('missing')
PY
)"
  echo "mio_any_item_shoe_state=$STATE poll=$i"
  if [ "$STATE" = ready ]; then
    python3 - "$JOB" "$ASSET" <<'PY'
import json,pathlib,sys
job=json.load(open(sys.argv[1],encoding='utf-8'))
asset=pathlib.Path(sys.argv[2])
out=job.get('output') or {}
rendered=out.get('renderedLayers') or []
pending=out.get('pendingLayers') or []
providers=out.get('providerOutputs') or []
assert 'shoes' in rendered, f'shoes_not_rendered:{rendered}'
assert 'shoes' not in pending, f'shoes_still_pending:{pending}'
assert asset.exists() and asset.stat().st_size > 1000, 'shoe_asset_missing'
shoe=next((r for r in providers if r.get('layer')=='shoes'),None)
provider=out.get('provider')
if shoe:
    provider_name=str(shoe.get('providerSpace'))
elif provider == 'real-render-cache':
    provider_name='real-render-cache'
else:
    raise AssertionError(f'shoe_provider_missing:{providers};provider={provider}')
print('mio_any_item_shoe_e2e=PASS')
print('mio_any_item_shoe_bytes='+str(asset.stat().st_size))
print('mio_any_item_provider='+provider_name)
PY
    OK=1
    break
  fi
  if [ "$STATE" = failed ]; then
    echo "mio_any_item_shoe_e2e=FAILED"
    cat "$JOB"
    journalctl --user -u agentos-mio-tryon-render-worker.service -n 100 --no-pager || true
    break
  fi
  sleep 2
done
test "$OK" -eq 1

echo "mio_tryon_deploy=PASS"
