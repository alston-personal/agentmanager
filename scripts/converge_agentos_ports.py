#!/usr/bin/env python3
"""Conservative port convergence: use existing unit authority; never guess service identity."""
import json,os,re,subprocess
from pathlib import Path
P=Path('/home/ubuntu/agent-data/config/port_registry.json')
def run(args,timeout=14):
 try:
  p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
  return p.returncode,p.stdout.strip()
 except Exception:return 99,''
def main():
 registry=json.loads(P.read_text())
 result={'schema':'agentos.port-converge/v1','started':[],'registered':[],'held':[]}
 # Only start installed systemd user units with a matching canonical owner and pre-existing release directory.
 for port,project,unit,folder in [(3040,'agentos-dashboard-blue','agentos-dashboard-blue.service','/home/ubuntu/agent-data/runtime/dashboard/blue'),(3041,'agentos-dashboard-green','agentos-dashboard-green.service','/home/ubuntu/agent-data/runtime/dashboard/green')]:
  if registry.get(str(port),{}).get('project')!=project:
   result['held'].append({'port':port,'reason':'registry_owner_mismatch'});continue
  if not Path(folder).is_dir() or not (Path(folder)/'package.json').exists():
   result['held'].append({'port':port,'reason':'release_missing'});continue
  rc,listener=run(['ss','-ltnH',f'sport = :{port}'])
  if listener:
   result['held'].append({'port':port,'reason':'already_listening'});continue
  # System manager uses ubuntu's user bus; never launch under root.
  base=['runuser','-u','ubuntu','--','env','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus','systemctl','--user']
  rc,v=run(base+['is-enabled',unit])
  if rc!=0 and v not in ('disabled','static'):
   result['held'].append({'port':port,'reason':'user_unit_unreachable','state':v});continue
  rc,out=run(base+(['enable','--now',unit] if v=='disabled' else ['start',unit]),timeout=25)
  rc2,listener=run(['ss','-ltnH',f'sport = :{port}'])
  if rc==0 and listener:result['started'].append({'port':port,'unit':unit})
  else:
   _,state=run(base+['show',unit,'-p','ActiveState','-p','SubState','-p','Result','-p','ExecMainStatus'])
   _,logs=run(['journalctl','--user','-u',unit,'-n','8','--no-pager'])
   result['held'].append({'port':port,'reason':'start_failed_or_no_listener','service_state':state[:400],'journal_tail':logs[-800:],'start_rc':rc})
 # Recover the verified existing LayoutLib Web unit under its actual owner, agentos-node.
 if registry.get('8766',{}).get('project')=='layoutlib-web':
  rc,listen=run(['ss','-ltnH','sport = :8766'])
  if not listen:
   import pwd
   u=pwd.getpwnam('agentos-node')
   uid=u.pw_uid
   unit=Path(u.pw_dir)/'.config/systemd/user/layoutlib-web.service'
   if unit.is_file() and '--port 8766' in unit.read_text() and (Path(u.pw_dir)/'projects/layoutlib/web_demo/server.py').is_file():
    base=['runuser','-u','agentos-node','--','env',f'XDG_RUNTIME_DIR=/run/user/{uid}',f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus','systemctl','--user']
    rc,out=run(base+['enable','--now','layoutlib-web.service'],timeout=28)
    rc2,listen=run(['ss','-ltnH','sport = :8766'])
    if rc==0 and listen:
     result['started'].append({'port':8766,'unit':'layoutlib-web.service','user':'agentos-node'})
    else:
     result['held'].append({'port':8766,'reason':'existing_unit_start_failed','status':out[-250:]})
   else:
    result['held'].append({'port':8766,'reason':'existing_unit_or_runtime_missing'})
 # Other registered ports: no guessing. Start only unit explicitly tied to port and current registry project.
 for port,project in [(3005,'if-tv-station'),(8800,'layoutlab-api')]:
  if registry.get(str(port),{}).get('project')!=project:continue
  rc,listener=run(['ss','-ltnH',f'sport = :{port}'])
  if listener:continue
  result['held'].append({'port':port,'project':project,'reason':'no_confirmed_owner_service_unit'})
 # Register only verified persistent Docker service port mappings.
 rc,docker=run(['docker','ps','--format','{{.Names}} {{.Ports}}'])
 known={18765:('vendor-reputation-service-api-1','vendor-reputation-api'),
        18766:('vendor-reputation-service-threads-reader-1','vendor-threads-reader'),
        8080:('vaultwarden','vaultwarden')}
 if rc==0:
  for port,(container,project) in known.items():
   matches=[line for line in docker.splitlines() if line.startswith(container+' ') and f':{port}->' in line]
   if len(matches)!=1:
    result['held'].append({'port':port,'reason':'container_mapping_not_confirmed'});continue
   existing=registry.get(str(port))
   if existing is not None:
    if existing.get('project')!=project:result['held'].append({'port':port,'reason':'registry_owner_conflict'})
    continue
   rc,out=run(['python3','/home/ubuntu/agentmanager/scripts/core_services/port_manager.py','register',str(port),project,'--desc','Verified persistent Docker port: '+container])
   if rc==0:result['registered'].append({'port':port,'project':project})
   else:result['held'].append({'port':port,'reason':'registration_failed'})
 # Never force-register unknown listening ports. Classify common persistent services for later reconciliation.
 rc,ss=run(['ss','-ltnpH'])
 for row in ss.splitlines():
  match=re.search(r':(\d+)\s',row)
  if not match:continue
  port=match.group(1)
  if port in registry:continue
  if int(port)>=32768:continue # ephemeral
  result['held'].append({'port':int(port),'reason':'listener_not_proven_canonical_project','process':row[-110:]})
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
