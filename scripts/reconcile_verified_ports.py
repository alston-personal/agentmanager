#!/usr/bin/env python3
"""Register verified persistent listeners, never assume an unknown PID or reassign a port."""
import json,re,subprocess
from pathlib import Path
reg=Path('/home/ubuntu/agent-data/config/port_registry.json')
registry=json.loads(reg.read_text())
verified={
 18767:('invoice-intake','invoice-intake.service'),
 18791:('openclaw-gateway','openclaw-gateway.service'),
 8095:('stitch-craft','stitch-craft.service'),
 8000:('agentos-chatgpt-mcp','agentos-chatgpt-mcp.service'),
 6080:('agentos-gui-novnc','agentos-gui-novnc.service'),
 5901:('agentos-gui-vnc','agentos-gui-vnc.service'),
}
p=subprocess.run(['ss','-ltnpH'],capture_output=True,text=True,check=True)
observed={}
for row in p.stdout.splitlines():
 parts=row.split()
 if len(parts)<4:continue
 m=re.search(r':(\d+)$',parts[3])
 if not m:continue
 port=int(m.group(1))
 pids=[int(x) for x in re.findall(r'pid=(\d+)',row)]
 observed.setdefault(port,set()).update(pids)
out={'schema':'agentos.verified-port-reconciliation/v1','registered':[],'already_registered':[],'held':[]}
for port,(project,unit) in verified.items():
 prior=registry.get(str(port))
 if prior:
  if prior.get('project')==project:out['already_registered'].append(port)
  else:out['held'].append({'port':port,'reason':'owner_conflict'})
  continue
 pids=observed.get(port,set())
 if not pids:
  out['held'].append({'port':port,'reason':'not_listening'});continue
 units=set()
 for pid in pids:
  try:
   cg=Path(f'/proc/{pid}/cgroup').read_text()
   units.update(re.findall(r'[a-zA-Z0-9_.@-]+\.service',cg))
  except OSError:pass
 if unit not in units:
  out['held'].append({'port':port,'reason':'unit_not_verified'});continue
 cmd=['python3','/home/ubuntu/agentmanager/scripts/core_services/port_manager.py','register',str(port),project,'--desc',f'Verified running systemd service {unit}']
 q=subprocess.run(cmd,capture_output=True,text=True)
 if q.returncode==0:out['registered'].append({'port':port,'project':project})
 else:out['held'].append({'port':port,'reason':'port_manager_rejected'})
print(json.dumps(out,ensure_ascii=False))
if out['held']:raise SystemExit(2)
