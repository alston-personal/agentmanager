#!/usr/bin/env python3
"""Restore Port Manager-owned LayoutLab API using existing source and existing layoutlib installation."""
import json,pathlib,pwd,subprocess,time
reg=pathlib.Path('/home/ubuntu/agent-data/config/port_registry.json')
source=pathlib.Path('/home/ubuntu/agentmanager/scripts/layoutlab_api.py')
layout=pathlib.Path('/home/agentos-node/projects/layoutlib/src/layoutlib')
def run(args,timeout=25):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 return p.returncode,(p.stdout+'\n'+p.stderr).strip()
assert json.loads(reg.read_text()).get('8800',{}).get('project')=='layoutlab-api','registry ownership mismatch'
assert source.is_file() and layout.is_dir(),'canonical source or dependency missing'
if run(['ss','-ltnH','sport = :8800'])[1]:
 raise RuntimeError('8800 already in use; refuse owner collision')
u=pwd.getpwnam('agentos-node')
unit=pathlib.Path(u.pw_dir)/'.config/systemd/user/layoutlab-api.service'
contents='''[Unit]
Description=LayoutLab API using canonical LayoutLib
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/agentmanager
Environment=PYTHONUNBUFFERED=1
Environment=LAYOUTLIB_ROOT=/home/agentos-node/projects/layoutlib
ExecStart=/usr/bin/python3 /home/ubuntu/agentmanager/scripts/layoutlab_api.py --host 127.0.0.1 --port 8800
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
'''
if unit.exists() and unit.read_text()!=contents:raise RuntimeError('existing unit conflict; no overwrite')
if not unit.exists():
 unit.write_text(contents)
 unit.chown(u.pw_uid,u.pw_gid)
base=['runuser','-u','agentos-node','--','env',f'XDG_RUNTIME_DIR=/run/user/{u.pw_uid}',f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{u.pw_uid}/bus','systemctl','--user']
for args in [base+['daemon-reload'],base+['enable','--now','layoutlab-api.service']]:
 rc,out=run(args)
 if rc:raise RuntimeError(out[-500:])
for _ in range(15):
 rc,out=run(['curl','-fsS','--max-time','3','http://127.0.0.1:8800/healthz'])
 if rc==0:
  obj=json.loads(out)
  if obj.get('ok') is True and obj.get('service')=='layoutlab-api':
   print(json.dumps({'status':'PASS','port':8800,'unit':'layoutlab-api.service','health':obj['service'],'public_routing_unchanged':True}))
   break
 time.sleep(2)
else:raise RuntimeError('8800 health failed')
