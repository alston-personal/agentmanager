#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, subprocess, urllib.request
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-commit',required=True)
    args=ap.parse_args()
    sha=args.source_commit.strip()
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise SystemExit('invalid source commit')
    root=Path.home()/'Library'/'Application Support'/'AgentOS'/'browser-bridge'
    root.mkdir(parents=True,exist_ok=True)
    agentos_root=Path.home()/'Library'/'Application Support'/'AgentOS'
    py=agentos_root/'venv'/'bin'/'python'
    if not py.exists():
        raise SystemExit('AgentOS runtime python missing')
    site=root/'site-packages'
    site.mkdir(parents=True,exist_ok=True)
    subprocess.run([str(py),'-m','pip','install','-q','--upgrade','--target',str(site),'playwright'],check=True,timeout=240)
    bridge=root/'threads_web_dm_bridge_user.py'
    urllib.request.urlretrieve(f'https://raw.githubusercontent.com/alston-personal/agentmanager/{sha}/scripts/threads_web_dm_bridge_user.py',bridge)
    os.chmod(bridge,0o700)
    runner=root/'bridge-runner.py'
    runner.write_text("import runpy,sys; from pathlib import Path; root=Path(__file__).resolve().parent; sys.path.insert(0,str(root/'site-packages')); runpy.run_path(str(root/'threads_web_dm_bridge_user.py'),run_name='__main__')\n",encoding='utf-8')
    os.chmod(runner,0o700)
    print('threads_web_dm_install=PASS')
    print('threads_web_dm_source_commit='+sha)
    return 0
if __name__=='__main__':
    raise SystemExit(main())
