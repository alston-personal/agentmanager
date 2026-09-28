#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import venv
from pathlib import Path

REPO='alston-personal/agentmanager'

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-commit',required=True)
    args=ap.parse_args()
    sha=args.source_commit.strip()
    if not re.fullmatch(r'[0-9a-f]{40}',sha):
        raise SystemExit('invalid source commit')

    root=Path.home()/'Library'/'Application Support'/'AgentOS'
    candidate=root/'versions'/sha
    py=candidate/'venv'/'bin'/'python'
    if not py.exists():
        candidate.mkdir(parents=True,exist_ok=True)
        venv.EnvBuilder(with_pip=True,clear=True).create(candidate/'venv')
        p=subprocess.run(
            [str(py),'-m','pip','install','-q','--upgrade',f'git+https://github.com/{REPO}.git@{sha}'],
            text=True,capture_output=True,timeout=240,check=False,
        )
        if p.returncode != 0:
            print(p.stderr[-2000:])
            raise SystemExit('candidate install failed')

    payload=json.dumps({
        'schema':'agentos.node-task/v0.1',
        'task_id':'bootstrap-macos-runtime',
        'action':'node.runtime.converge',
        'phase':'stage',
        'source_commit':sha,
        'cognition_ids_used':[],
    },separators=(',',':'))
    code=(
        "import json;"
        "from agentos_node.client_runtime_converge import execute_client_runtime_converge;"
        f"task=json.loads({payload!r});"
        "print(json.dumps(execute_client_runtime_converge(task),sort_keys=True))"
    )
    p=subprocess.run([str(py),'-c',code],text=True,capture_output=True,timeout=90,check=False)
    print(p.stdout,end='')
    if p.returncode != 0:
        print(p.stderr[-2000:])
        raise SystemExit(p.returncode)
    if 'awaiting-controller-acceptance' not in p.stdout:
        raise SystemExit('candidate did not enter awaiting-controller-acceptance')
    print('agentos_macos_transactional_bootstrap=PASS')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
