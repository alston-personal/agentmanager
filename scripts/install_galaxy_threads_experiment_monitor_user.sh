#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "galaxy_experiment_monitor_install=WRONG_USER" >&2
  exit 2
fi

REPO="${AGENTOS_REPO:-$HOME/agentmanager}"
SOURCE_COMMIT="${AGENTOS_SOURCE_COMMIT:-}"
# This installer executes as ubuntu. Materialize its companion scripts from the
# immutable triggering commit here, instead of requiring the agentos-node
# runner identity to overwrite ubuntu-owned live files.
if printf '%s' "$SOURCE_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
  for rel in \
    scripts/monitor_galaxy_threads_experiment_user.py \
    scripts/sync_sunlake_milkcat_persona_user.py \
    scripts/evolve_mio_persona_ir_user.py \
    scripts/mio_persona_social_loop_user.py \
    scripts/diagnose_mio_threads_search_scope_user.py \
    agentos_node/persona_life.py; do
    tmp="$(mktemp)"
    git -C "$REPO" show "$SOURCE_COMMIT:$rel" > "$tmp"
    install -m 0644 "$tmp" "$REPO/$rel"
    rm -f "$tmp"
  done
  echo "galaxy_experiment_monitor_companions=SYNCED_FROM_SOURCE_COMMIT"
fi
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE="$UNIT_DIR/agentos-galaxy-experiment-monitor.service"
TIMER="$UNIT_DIR/agentos-galaxy-experiment-monitor.timer"
LOG_DIR="$HOME/agent-data/logs"
LOG="$LOG_DIR/galaxy-experiment-monitor.log"

test -f "$REPO/scripts/monitor_galaxy_threads_experiment_user.py"
test -f "$REPO/scripts/sync_sunlake_milkcat_persona_user.py"
test -f "$REPO/scripts/evolve_mio_persona_ir_user.py"
test -f "$REPO/scripts/mio_persona_social_loop_user.py"
mkdir -p "$UNIT_DIR" "$LOG_DIR"

# Diagnose the real ubuntu-owned relay executor; do not expose binary paths,
# account state, credentials, model output, or user-private files.
PYTHONPATH="$REPO" python3 - <<'PY'
from pathlib import Path
from agentos_node.antigravity_relay_worker import discover_executor
for provider in ('claude','agy'):
    try:
        _, selected=discover_executor(provider)
        available=bool(selected and Path(selected[0]).is_file())
    except Exception:
        available=False
    print('mio_relay_'+provider+'_available='+str(available).lower())
PY
if systemctl --user is-active --quiet agentos-antigravity-relay.service; then
  echo 'mio_relay_service=ACTIVE'
else
  echo 'mio_relay_service=INACTIVE'
fi
# Inspect only public-free relay queue state, never a capsule's instruction or stdout.
python3 - <<'PY'
import json,re
from pathlib import Path
pending=Path('/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/decision-pending.json')
root=Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
try: cid=str(json.loads(pending.read_text(encoding='utf-8')).get('capsule_id') or '')
except (FileNotFoundError,ValueError): cid=''
if not re.fullmatch(r'relay-[0-9a-f]{32}',cid):
    state='no_pending'
elif (root/'receipts'/f'{cid}.json').is_file():
    state='receipt_ready'
elif (root/'processing'/f'{cid}.json').is_file():
    state='processing'
elif (root/'inbox'/f'{cid}.json').is_file():
    state='queued'
else:
    state='missing'
print('mio_relay_capsule_state='+state)
probe=Path('/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat/relay-probe.json')
try: test=json.loads(probe.read_text(encoding='utf-8'))
except (FileNotFoundError,ValueError): test={}
probe_id=str(test.get('capsule_id') or '')
if test.get('status')=='pass':
    probe_state='pass'
elif re.fullmatch(r'relay-[0-9a-f]{32}',probe_id):
    if (root/'receipts'/f'{probe_id}.json').is_file(): probe_state='receipt_ready'
    elif (root/'processing'/f'{probe_id}.json').is_file(): probe_state='processing'
    elif (root/'inbox'/f'{probe_id}.json').is_file(): probe_state='queued'
    else: probe_state='missing'
else:
    probe_state='not_submitted'
print('mio_relay_probe_state='+probe_state)
PY
# Check whether the separately installed, already allowlisted AGY executor can
# answer a harmless JSON prompt. Bounded, one check per six hours; never print
# its model output, login state, file locations or any credential.
python3 - "$REPO" <<'PY'
import json,os,subprocess,sys,time
from pathlib import Path
from agentos_node.antigravity_relay_worker import discover_executor
repo=Path(sys.argv[1])
state=Path('/home/ubuntu/agent-data/runtime/social/experiments/ai-subscription/agy-health.json')
try: old=json.loads(state.read_text(encoding='utf-8'))
except (FileNotFoundError,ValueError): old={}
if time.time()-float(old.get('checked_unix') or 0)<21600:
    print('mio_agy_probe='+str(old.get('result') or 'unknown'))
else:
    result='unavailable'
    try:
        _,executor=discover_executor('agy')
        if executor:
            prompt='PRIVATE HEALTH CHECK: return exactly {"ok":true} as JSON. No tools, no external actions.'
            r=subprocess.run([*executor,'run','--task',prompt,'--workspace',str(repo)],cwd=str(repo),capture_output=True,text=True,timeout=25,check=False)
            if r.returncode:
                result='nonzero_exit'
            elif '"ok"' in r.stdout and 'true' in r.stdout.lower():
                result='pass'
            else:
                result='unexpected_output'
    except subprocess.TimeoutExpired: result='timeout'
    except OSError: result='spawn_error'
    state.parent.mkdir(parents=True,exist_ok=True)
    state.write_text(json.dumps({'checked_unix':time.time(),'result':result})+'\n',encoding='utf-8')
    os.chmod(state,0o600)
    print('mio_agy_probe='+result)
PY
# Give Mio her own ubuntu-owned AGY relay. Never change the shared
# Antigravity/Claude worker or other AgentOS projects' model provider.
MIO_RELAY_ROOT="$HOME/agent-data/runtime/mio-antigravity-relay"
MIO_RELAY_UNIT="$UNIT_DIR/agentos-mio-agy-relay.service"
test "$(python3 - "$HOME/agent-data/runtime/social/experiments/ai-subscription/agy-health.json" <<'PY'
import json,sys,time
try: s=json.load(open(sys.argv[1],encoding='utf-8'))
except (FileNotFoundError,ValueError): s={}
print('yes' if s.get('result')=='pass' and time.time()-float(s.get('checked_unix') or 0)<21600 else 'no')
PY
)" = yes || { echo 'mio_agy_relay=PROBE_NOT_PASS'; exit 5; }
cat > "$MIO_RELAY_UNIT" <<EOF
[Unit]
Description=AgentOS Mio Private AGY Persona Decision Relay
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO
Environment=PYTHONPATH=$REPO
UMask=0007
ExecStart=/usr/bin/python3 -m agentos_node.antigravity_relay_worker --provider agy --root $MIO_RELAY_ROOT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now agentos-mio-agy-relay.service >/dev/null
systemctl --user is-active --quiet agentos-mio-agy-relay.service
echo 'mio_agy_relay=ACTIVE'
# Read-only scope diagnostics; never log access tokens or OAuth responses.
PYTHONPATH="$REPO" python3 "$REPO/scripts/diagnose_mio_threads_search_scope_user.py" || echo 'mio_search_scope_probe=unavailable'
# Relay restart is a targeted repair, not part of normal monitor reinstallation.
# Keep the background executor undisturbed during subsequent code deployments.


cat > "$SERVICE" <<EOF
[Unit]
Description=AgentOS Threads AI Subscription Experiment Monitor
After=network-online.target agentos-social-runtime.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$REPO
Environment=AGENTOS_MIO_RELAY_ROOT=$MIO_RELAY_ROOT
ExecStart=/usr/bin/python3 $REPO/scripts/monitor_galaxy_threads_experiment_user.py
# Order is causal: observe -> persist event -> evolve current self -> decide/reply.
# If canonical sync/evolution fails, do not answer from stale or isolated context.
ExecStartPost=/bin/sh -c '/usr/bin/python3 $REPO/scripts/sync_sunlake_milkcat_persona_user.py && /usr/bin/python3 $REPO/scripts/evolve_mio_persona_ir_user.py && /usr/bin/python3 $REPO/scripts/mio_persona_social_loop_user.py || { echo mio_persona_cycle=DEFERRED; exit 0; }'
StandardOutput=append:$LOG
StandardError=append:$LOG

[Install]
WantedBy=default.target
EOF

cat > "$TIMER" <<EOF
[Unit]
Description=Monitor Threads AI Subscription Experiment

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true
Unit=agentos-galaxy-experiment-monitor.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agentos-galaxy-experiment-monitor.timer >/dev/null
if ! systemctl --user start agentos-galaxy-experiment-monitor.service; then
  systemctl --user --no-pager --full status agentos-galaxy-experiment-monitor.service >&2 || true
  journalctl --user -u agentos-galaxy-experiment-monitor.service -n 80 --no-pager >&2 || true
  if [ -f "$LOG" ]; then
    echo "--- galaxy monitor log tail ---" >&2
    tail -n 80 "$LOG" >&2 || true
  fi
  echo "galaxy_experiment_monitor_initial_run=FAIL" >&2
  exit 4
fi
systemctl --user is-enabled --quiet agentos-galaxy-experiment-monitor.timer
systemctl --user is-active --quiet agentos-galaxy-experiment-monitor.timer

# Emit only IDs for the newly observed reader comment; never expose the
# surrounding private monitor snapshot or other commenters in run logs.
python3 - <<'PY'
import json
from pathlib import Path
catalog=Path('/tmp/agentos-social-public/sunlake-milkcat-replies.json')
if catalog.is_file():
    doc=json.loads(catalog.read_text(encoding='utf-8'))
    item=next((x for x in (doc.get('replies') or []) if str(x.get('id') or '')=='18124006117843631'),None)
    if item:
        print('mio_latest_comment_id='+str(item['id']))
        print('mio_latest_comment_root_id='+str(item.get('root_post_id') or ''))
        print('mio_latest_comment_replied_to_id='+str(item.get('replied_to_id') or ''))
        print('mio_latest_comment_owned='+str(bool(item.get('is_reply_owned_by_me'))).lower())
PY

SNAPSHOT="$HOME/agent-data/runtime/social/experiments/ai-subscription/latest.json"
test -f "$SNAPSHOT"
python3 - "$SNAPSHOT" <<'PY'
import json, sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
assert p.get('schema')=='agentos.social-experiment-snapshot/v1',p
assert p.get('experiment')=='ai-pays-its-subscription',p
print('galaxy_experiment_monitor_snapshot=PASS')
print('galaxy_experiment_monitor_reply_count='+str(p.get('reply_count',0)))
print('galaxy_experiment_monitor_new_replies='+str(len(p.get('new_replies') or [])))
print('galaxy_experiment_monitor_needs_attention='+str(bool(p.get('needs_attention'))).lower())
PY

HISTORY="$HOME/agent-data/runtime/social/experiments/ai-subscription/history.jsonl"
if [ -f "$HISTORY" ]; then
python3 - "$HISTORY" <<'PY'
import json, sys
seen={}
for raw in open(sys.argv[1],encoding='utf-8'):
    try: row=json.loads(raw)
    except Exception: continue
    for item in row.get('new_replies') or []:
        rid=str(item.get('id') or '')
        if rid:
            seen[rid]={
              'id':rid,
              'username':item.get('username'),
              'text':item.get('text'),
              'timestamp':item.get('timestamp'),
              'permalink':item.get('permalink'),
            }
print('galaxy_experiment_monitor_reply_catalog='+json.dumps(list(seen.values()),ensure_ascii=False,separators=(',',':')))
PY
fi

echo "galaxy_experiment_monitor_install=PASS"
echo "galaxy_experiment_monitor_interval=10m"
echo "galaxy_experiment_monitor_log=$LOG"
if [ -f "$LOG" ]; then
  tail -n 220 "$LOG" | grep -E '^(galaxy_monitor=|galaxy_monitor_reply_count=|galaxy_monitor_new_replies=|persona_git_sync=|persona_git_sync_added=|mio_persona_ir_evolve=|mio_persona_ir_revision=|mio_persona_ir_new_events=|mio_persona_ir_new_growth=|mio_persona_cycle=|mio_social_loop=|mio_social_decision=|mio_social_publish=|mio_social_pending=|mio_social_new_external=|mio_social_outbound=|mio_social_outbound_today=|mio_life_event=|mio_energy=)' | tail -n 80 || true
fi
python3 - <<'PY'
import json
from pathlib import Path
p=Path('/tmp/agentos-social-public/sunlake-milkcat-replies.json')
try: d=json.loads(p.read_text(encoding='utf-8'))
except (FileNotFoundError,ValueError): d={}
print('mio_public_export_owned_posts='+str(len(d.get('owned_posts') or [])))
print('mio_public_export_replies='+str(len(d.get('replies') or [])))
PY
