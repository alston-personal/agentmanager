#!/usr/bin/env python3
"""Read-only Oracle port ownership and runtime audit. Never mutates services or config."""
import json, os, re, subprocess
from pathlib import Path

REG = Path("/home/ubuntu/agent-data/config/port_registry.json")
def cmd(args, timeout=12):
    try:
        p=subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"rc":p.returncode,"stdout":p.stdout,"stderr_type":"permission_or_command_error" if p.returncode else ""}
    except Exception as e:
        return {"rc":-1,"stdout":"","stderr_type":type(e).__name__}
def main():
    result={"schema":"agentos.port-runtime-audit/v1","read_only":True,
            "registry_available":REG.is_file(),"registry":{},"listeners":[],
            "nginx_agentos_routes":[],"unmatched_registry":[],"unregistered_listeners":[],
            "version":{},"warnings":[]}
    if REG.is_file():
        reg=json.loads(REG.read_text())
        if not isinstance(reg,dict): raise RuntimeError("invalid_registry")
        result["registry"]={str(k):{"project":v.get("project"),"description":v.get("description"),
               "updated_at":v.get("updated_at"),"migration":v.get("migration")} for k,v in reg.items() if isinstance(v,dict)}
    else: result["warnings"].append("registry_missing")
    ss=cmd(["ss","-ltnpH"])
    listeners={}
    for line in ss["stdout"].splitlines():
        parts=line.split()
        if len(parts)<5: continue
        address=parts[3]
        m=re.search(r":(\d+)$",address)
        if not m: continue
        port=m.group(1)
        listeners.setdefault(port,[]).append({"bind":address,"process":parts[5][:200] if len(parts)>5 else "unavailable"})
    for port,rows in sorted(listeners.items(),key=lambda p:int(p[0])):
        result["listeners"].append({"port":int(port),"owners":rows,"registry_project":result["registry"].get(port,{}).get("project")})
        if port not in result["registry"]: result["unregistered_listeners"].append(int(port))
    for port,owner in result["registry"].items():
        if port not in listeners: result["unmatched_registry"].append({"port":int(port),"project":owner.get("project")})
    # Inspect effective configuration; emit only routing lines, not the full file.
    ngx=cmd(["nginx","-T"])
    if ngx["rc"] != 0: result["warnings"].append("nginx_T_unavailable")
    for line in ngx["stdout"].splitlines():
        s=line.strip()
        if (s.startswith("location ") and ("agentos" in s or "dashboard" in s)) or (s.startswith("proxy_pass ") and re.search(r"(?<!\d)(3000|3041|8780)(?!\d)",s)):
            result["nginx_agentos_routes"].append(s[:250])
    for label,port in [("gateway_current",3000),("gateway_legacy_candidate",3041),("one",8780)]:
        p=cmd(["curl","-sS","--max-time","3","-o","/dev/null","-w","%{http_code}",f"http://127.0.0.1:{port}/dashboard/api/agentos/v1/health" if port!=8780 else f"http://127.0.0.1:{port}/v1/health"])
        result[label]={"http":p["stdout"].strip(),"registry_project":result["registry"].get(str(port),{}).get("project"),"listening":str(port) in listeners}
    p=cmd(["git","-C","/home/ubuntu/agentmanager","rev-parse","HEAD"])
    result["version"]["oracle_checkout_head"]=p["stdout"].strip() if p["rc"]==0 else None
    p=cmd(["systemctl","--user","show","agentos-dashboard.service","-p","FragmentPath","-p","ActiveState","-p","ExecStart","-p","Environment"])
    result["version"]["dashboard_unit"]=p["stdout"][:1600] if p["rc"]==0 else "unavailable"
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
