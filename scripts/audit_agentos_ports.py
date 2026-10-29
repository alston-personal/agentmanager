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
    active_file = ""
    for line in ngx["stdout"].splitlines():
        if line.startswith("# configuration file "): active_file = line[21:].split(":",1)[0]
        if "3041" in line or "3040" in line:
            result.setdefault("upstream_definitions",[]).append({"file":active_file,"directive":line.strip()[:240]})
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
    # Reboot persistence and blue/green launch authority (read-only).
    probes={
      "system_services": ["systemctl","list-unit-files","--no-pager","--no-legend"],
      "user_services": ["runuser","-u","ubuntu","--","systemctl","--user","list-unit-files","--no-pager","--no-legend"],
      "service_processes": ["ps","-eo","pid,user,args"],
      "boot_timestamp": ["uptime","-s"],
    }
    result["boot_recovery"]={}
    for key,args in probes.items():
        p=cmd(args)
        lines=p["stdout"].splitlines()
        if key=="system_services" or key=="user_services":
            lines=[x for x in lines if any(k in x.lower() for k in ("dashboard","blue","green","milkcat","gateway","agentos"))]
        elif key=="service_processes":
            lines=[x[:300] for x in lines if any(k in x.lower() for k in ("next-server","dashboard","blue","green")) and "audit_agentos_ports" not in x]
        result["boot_recovery"][key]={"rc":p["rc"],"lines":lines[:100]}
    roots=["/home/ubuntu/.config/systemd/user","/etc/systemd/system"]
    result["boot_recovery"]["matching_unit_files"]=[]
    for root in roots:
        d=Path(root)
        if d.exists():
            for x in d.glob("*dashboard*"):
                if x.is_file():
                    content=x.read_text(errors="replace")
                    result["boot_recovery"]["matching_unit_files"].append({"path":str(x),"contents":[line for line in content.splitlines() if any(k in line for k in ("ExecStart","Restart=","WantedBy=","Environment=","WorkingDirectory="))][:20]})
    result["slot_health"]={}
    for port in [3000,3040,3041]:
        for path in ["/dashboard/api/agentos/v1/health","/dashboard/api/auth/session"]:
            x=cmd(["curl","-sS","--max-time","5","-o","/dev/null","-w","%{http_code}",f"http://127.0.0.1:{port}{path}"])
            result["slot_health"][f"{port}:{path}"]={"code":x["stdout"].strip(),"rc":x["rc"]}
    pub=cmd(["curl","-sS","--max-time","7","-o","/dev/null","-w","%{http_code}","https://studio.milkcat.org/dashboard/api/agentos/v1/health"])
    result["slot_health"]["public_one_health"]={"code":pub["stdout"].strip(),"rc":pub["rc"]}
    result["service_ownership"]={}
    for port in [3005,8766,8800,3040,3041,3030,8765,8767,18765,18766,18767,18791]:
        row=next((r for r in result["listeners"] if r["port"]==port),None)
        result["service_ownership"][str(port)]={"listener":row,"registry":result["registry"].get(str(port))}
    result["boot_persistence"]={}
    for unit in ["agentos-dashboard-blue.service","agentos-dashboard-green.service","agentos-dashboard.service"]:
        base=["runuser","-u","ubuntu","--","env","XDG_RUNTIME_DIR=/run/user/1001","DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus","systemctl","--user"]
        status=cmd(base+["show",unit,"-p","UnitFileState","-p","ActiveState","-p","SubState","-p","Result","-p","FragmentPath"])
        result["boot_persistence"][unit]={"rc":status["rc"],"state":status["stdout"][:600]}
    linger=cmd(["loginctl","show-user","ubuntu","-p","Linger","-p","State"])
    result["boot_persistence"]["user_linger"]={"rc":linger["rc"],"state":linger["stdout"][:200]}
    result["unregistered_identity"]=[]
    for row in result["listeners"]:
        port=row["port"]
        if str(port) in result["registry"] or port not in [3030,8765,8767,18765,18766,18767,18791,8080,8090,8095,8099]:
            continue
        process=row["owners"][0].get("process","")
        m=re.search(r"pid=(\\d+)",process)
        pid=m.group(1) if m else None
        argv=Path("/proc/"+pid+"/cmdline") if pid else None
        try: cmdline=argv.read_bytes().replace(b"\\x00",b" ").decode(errors="replace")[:280] if argv else None
        except Exception: cmdline=None
        result["unregistered_identity"].append({"port":port,"pid":pid,"command":cmdline})
    d=cmd(["docker","ps","--format","{{.Names}} {{.Ports}}"])
    result["docker_port_map"]={"rc":d["rc"],"lines":d["stdout"].splitlines()[:45]}
    result["missing_service_sources"]={}
    for port,label in [(3005,"if-tv-station"),(8766,"layoutlib-web"),(8800,"layoutlab-api")]:
        found=[]
        for root in [Path("/etc/systemd/system"),Path("/home/ubuntu/.config/systemd/user"),Path("/home/agentos-node/.config/systemd/user")]:
            if not root.exists(): continue
            for unit in root.glob("*.service"):
                if label in unit.name.lower() or str(port) in unit.read_text(errors="replace"):
                    found.append({"file":str(unit),"relevant_lines":[line[:200] for line in unit.read_text(errors="replace").splitlines() if any(k in line for k in ("ExecStart","WorkingDirectory","Environment=PORT","Restart="))][:8]})
        result["missing_service_sources"][str(port)]={"units":found}
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
