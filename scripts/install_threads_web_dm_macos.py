#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, subprocess, urllib.request, venv
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-commit',required=True)
    args=ap.parse_args()
    sha=args.source_commit.strip()
    if len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):
        raise SystemExit('invalid source commit')
    root=Path.home()/'Library'/'Application Support'/'AgentOS'/'browser-bridge'
    venv_dir=root/'venv'
    root.mkdir(parents=True,exist_ok=True)
    if not (venv_dir/'bin'/'python').exists():
        venv.EnvBuilder(with_pip=True).create(venv_dir)
    py=str(venv_dir/'bin'/'python')
    subprocess.run([py,'-m','pip','install','-q','--upgrade','pip'],check=True,timeout=120)
    subprocess.run([py,'-m','pip','install','-q','--upgrade',f'git+https://github.com/alston-personal/agentmanager.git@{sha}','playwright'],check=True,timeout=240)
    bridge=root/'threads_web_dm_bridge_user.py'
    urllib.request.urlretrieve(f'https://raw.githubusercontent.com/alston-personal/agentmanager/{sha}/scripts/threads_web_dm_bridge_user.py',bridge)
    os.chmod(bridge,0o700)
    print('threads_web_dm_install=PASS')
    print('threads_web_dm_source_commit='+sha)
    return 0
if __name__=='__main__':
    raise SystemExit(main())
