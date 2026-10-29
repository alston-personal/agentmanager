#!/usr/bin/env python3
"""Restore the existing IF TV Next.js runtime under a systemd user unit."""
import json,os,pathlib,pwd,subprocess,time
root=pathlib.Path('/home/ubuntu/if-tv-station')
reg=pathlib.Path('/home/ubuntu/agent-data/config/port_registry.json')
def run(args,timeout=25):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 return p.returncode,(p.stdout+'\n'+p.stderr).strip()
result={'service':'if-tv-station','port':3005,'status':'unverified'}
assert json.loads(reg.read_text()).get('3005',{}).get('project')=='if-tv-station'
p=json.loads((root/'package.json').read_text())
assert p.get('scripts',{}).get('start')=='next start'
assert (root/'.next').is_dir() and (root/'node_modules/.bin/next').exists()
u=pwd.getpwnam('ubuntu'); uid=u.pw_uid
unit=pathlib.Path(u.pw_dir)/'.config/systemd/user/if-tv-station.service'
content='''[Unit]
Description=IF TV Station existing Next.js runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/ubuntu/if-tv-station
Environment=NODE_ENV=production
Environment=PORT=3005
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
'''
if unit.exists() and unit.read_text()!=content:
 raise RuntimeError('Existing unit differs: refusing overwrite')
if not unit.exists():unit.write_text(content)
base=['runuser','-u','ubuntu','--','env',f'XDG_RUNTIME_DIR=/run/user/{uid}',f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus','systemctl','--user']
for args in [base+['daemon-reload'],base+['enable','--now','if-tv-station.service']]:
 rc,out=run(args)
 if rc:raise RuntimeError(out[-400:])
for _ in range(18):
 rc,code=run(['curl','-sS','--max-time','4','-o','/dev/null','-w','%{http_code}','http://127.0.0.1:3005/iftv'])
 if rc==0 and code in ['200','301','302','307','308']:break
 time.sleep(2)
else: raise RuntimeError('IF TV local /iftv health failed')
rc,pub=run(['curl','-sS','--max-time','10','-o','/dev/null','-w','%{http_code}','https://studio.milkcat.org/iftv'])
result.update({'unit':'if-tv-station.service','local_http':code,'public_http':pub,'status':'PASS' if rc==0 and pub in ['200','301','302','307','308'] else 'PUBLIC_UNVERIFIED'})
print(json.dumps(result))
if result['status']!='PASS':raise SystemExit(2)
