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
  rc,v=run(['runuser','-u','ubuntu','--','systemctl','--user','is-enabled',unit])
  if rc!=0:
   result['held'].append({'port':port,'reason':'user_unit_not_enabled_or_unreachable'});continue
  rc,_=run(['runuser','-u','ubuntu','--','systemctl','--user','start',unit],timeout=25)
  rc2,listener=run(['ss','-ltnH',f'sport = :{port}'])
  if rc==0 and listener:result['started'].append({'port':port,'unit':unit})
  else:result['held'].append({'port':port,'reason':'start_failed_or_no_listener'})
 # Other registered ports: no guessing. Start only unit explicitly tied to port and current registry project.
 for port,project in [(3005,'if-tv-station'),(8766,'layoutlib-web'),(8800,'layoutlab-api')]:
  if registry.get(str(port),{}).get('project')!=project:continue
  rc,listener=run(['ss','-ltnH',f'sport = :{port}'])
  if listener:continue
  result['held'].append({'port':port,'project':project,'reason':'no_confirmed_owner_service_unit'})
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
