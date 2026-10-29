#!/usr/bin/env python3
"""Emergency dashboard failover from dead green 3041 to verified canonical 3000."""
import json,re,shutil,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
CFG=Path("/etc/nginx/sites-available/studio.milkcat.org")
REG=Path("/home/ubuntu/agent-data/config/port_registry.json")
PUBLIC="https://studio.milkcat.org/dashboard/api/agentos/v1/health"
LOCAL="http://127.0.0.1:3000/dashboard/api/agentos/v1/health"
def run(*a):
 p=subprocess.run(a,capture_output=True,text=True,timeout=18)
 if p.returncode: raise RuntimeError(f"{a[0]} failed rc={p.returncode} stderr={p.stderr[-220:]}")
 return p.stdout
def get(url):
 j=json.loads(run("curl","-fsS","--max-time","7",url))
 if j.get("ok") is not True or j.get("realm_id")!="realm-alston": raise RuntimeError("Wrong ONE realm")
 return j
def main():
 reg=json.loads(REG.read_text())
 assert reg.get("3000",{}).get("project")=="agentos-dashboard","port_3000_owner_invalid"
 assert reg.get("3041",{}).get("project")=="agentos-dashboard-green","port_3041_owner_invalid"
 get(LOCAL)
 current=CFG.read_text()
 old="proxy_pass http://127.0.0.1:3041;"
 new="proxy_pass http://127.0.0.1:3000;"
 # Exact known target only, and only when a /dashboard location is its enclosing block.
 hits=list(re.finditer(re.escape(old),current))
 if len(hits)!=1: raise RuntimeError(f"expected_exactly_one_green_upstream_found_{len(hits)}")
 at=hits[0].start()
 opens=list(re.finditer(r"(?m)^\s*location\s+(?:\^~\s+)?(/dashboard/?|/dashboard/api/agentos/?)\s*\{",current[:at]))
 if not opens: raise RuntimeError("not_in_known_dashboard_location")
 o=opens[-1]; segment=current[o.end():at]
 if segment.count("{")!=segment.count("}"): raise RuntimeError("target_not_inside_direct_location")
 if re.search(r"(?m)^\s*}\s*$",segment): raise RuntimeError("location_closed_before_proxy")
 # Old green must be down; do not override a healthy blue/green deployment.
 p=subprocess.run(["curl","-sS","--max-time","3","-o","/dev/null","-w","%{http_code}","http://127.0.0.1:3041/dashboard/api/agentos/v1/health"],capture_output=True,text=True,timeout=6)
 if p.stdout.strip()=="200": raise RuntimeError("green_is_healthy_abort_failover")
 backup=CFG.with_name(CFG.name+".agentos-failover."+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".bak")
 shutil.copy2(CFG,backup)
 try:
  CFG.write_text(current[:at]+new+current[at+len(old):])
  run("nginx","-t")
  run("systemctl","reload","nginx")
  time.sleep(1)
  get(PUBLIC)
 except Exception:
  shutil.copy2(backup,CFG)
  run("nginx","-t")
  run("systemctl","reload","nginx")
  raise
 print(json.dumps({"schema":"agentos.one-emergency-failover/v1","ok":True,"from":"agentos-dashboard-green:3041","to":"agentos-dashboard:3000","backup":backup.name,"public_health":"PASS","blue_green_registry_preserved":True}))
if __name__=="__main__": main()
