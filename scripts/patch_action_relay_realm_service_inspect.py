#!/usr/bin/env python3
from pathlib import Path

path=Path('agentos_node/action_relay.py')
text=path.read_text(encoding='utf-8')
marker='realm_fabric_service_attestation_v1'
if marker in text:
    print('realm_service_inspect_patch=ALREADY_PRESENT')
    raise SystemExit(0)

anchor='\ndef _layoutlab_api_restart(params: dict[str, Any]) -> dict[str, Any]:\n'
if anchor not in text:
    raise SystemExit('service action anchor missing')
func=r'''

# realm_fabric_service_attestation_v1
def _inspect_realm_fabric_service(params: dict[str, Any]) -> dict[str, Any]:
    if params not in ({},):
        raise ValueError('unexpected parameters')
    steps=[]
    show=_run([
        'systemctl','--user','show','agentos-realm-fabric.service',
        '--property=ActiveState','--property=SubState','--property=MainPID',
        '--property=ExecMainStatus','--property=ExecMainCode','--property=ExecStart',
    ], cwd=Path.home(), timeout=15)
    steps.append({'step':'systemd_show',**show})
    status=_run(['systemctl','--user','status','agentos-realm-fabric.service','--no-pager','-l'], cwd=Path.home(), timeout=15)
    steps.append({'step':'systemd_status',**status})
    proc=_run(['pgrep','-af','agent_core.realm_cli serve'], cwd=Path.home(), timeout=10)
    steps.append({'step':'processes',**proc})
    log_path=Path('/home/ubuntu/agent-data/logs/realm-fabric.log')
    log_tail=''
    if log_path.is_file():
        try:
            lines=log_path.read_text(encoding='utf-8',errors='replace').splitlines()
            log_tail='\n'.join(lines[-160:])[-20000:]
        except OSError as exc:
            log_tail=type(exc).__name__+': '+str(exc)
    fields={}
    for raw in (show.get('stdout') or '').splitlines():
        if '=' in raw:
            k,v=raw.split('=',1); fields[k]=v
    return {
        'ok': True,
        'service': 'agentos-realm-fabric.service',
        'configured_core_commit': _observed_realm_commit(),
        'active_state': fields.get('ActiveState'),
        'sub_state': fields.get('SubState'),
        'main_pid': int(fields.get('MainPID') or 0),
        'exec_main_status': fields.get('ExecMainStatus'),
        'exec_main_code': fields.get('ExecMainCode'),
        'log_tail': log_tail,
        'steps': steps,
    }
'''
text=text.replace(anchor,func+anchor,1)
mapping='    "agentos.realm-fabric.deployment_status": _realm_fabric_deployment_status,\n'
if mapping not in text:
    raise SystemExit('deployment action mapping missing')
text=text.replace(mapping,mapping+'    "agentos.realm-fabric.inspect_service": _inspect_realm_fabric_service,\n',1)
compile(text,str(path),'exec')
path.write_text(text,encoding='utf-8')
print('realm_service_inspect_patch=PASS')
