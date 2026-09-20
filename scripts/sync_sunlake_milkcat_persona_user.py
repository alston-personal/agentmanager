#!/usr/bin/env python3
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

DATA_REPO=Path('/home/ubuntu/agent-data')
EXPORT=Path('/tmp/agentos-social-public/sunlake-milkcat-replies.json')
EVENTS_REL=Path('personas/sunlake-milkcat/events/events.jsonl')
CHARACTER_ID='sunlake-milkcat-ai-001'

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def run(args, cwd=None, check=True):
    p=subprocess.run(args,cwd=cwd,text=True,capture_output=True,timeout=60,check=False)
    if check and p.returncode!=0:
        raise RuntimeError('git_operation_failed')
    return p

def main():
    if os.geteuid()!=1001 or (os.environ.get('USER') not in (None,'ubuntu')):
        print('persona_git_sync=WRONG_USER',file=sys.stderr); return 2
    if not EXPORT.is_file():
        print('persona_git_sync=NO_EXPORT'); return 0
    if not (DATA_REPO/'.git').exists():
        print('persona_git_sync=DATA_REPO_MISSING',file=sys.stderr); return 3

    remote=run(['git','remote','get-url','origin'],cwd=DATA_REPO).stdout.strip()
    safe=remote.rstrip('/').removesuffix('.git')
    if not safe.endswith('/my-agent-data') and not safe.endswith(':alston-personal/my-agent-data'):
        print('persona_git_sync=UNEXPECTED_REMOTE',file=sys.stderr); return 4

    payload=json.loads(EXPORT.read_text(encoding='utf-8'))
    if payload.get('schema')!='agentos.social-public-reply-export/v1':
        print('persona_git_sync=BAD_EXPORT_SCHEMA',file=sys.stderr); return 5

    run(['git','fetch','origin','main'],cwd=DATA_REPO)
    root=Path(tempfile.mkdtemp(prefix='agentos-persona-sync-'))
    work=root/'work'
    try:
        run(['git','worktree','add','--detach',str(work),'origin/main'],cwd=DATA_REPO)
        events=work/EVENTS_REL
        if not events.is_file():
            print('persona_git_sync=PERSONA_IR_MISSING',file=sys.stderr); return 6
        existing=set()
        for raw in events.read_text(encoding='utf-8').splitlines():
            try: row=json.loads(raw)
            except Exception: continue
            if row.get('platform')=='threads' and row.get('object_id'):
                existing.add(str(row['object_id']))

        account=str(payload.get('account_username') or '').lower()
        added=[]
        for item in payload.get('replies') or []:
            rid=str(item.get('id') or '')
            if not rid or rid in existing: continue
            author=str(item.get('username') or '')
            own=bool(account) and author.lstrip('@').lower()==account.lstrip('@')
            row={
              'schema':'agentos.persona-event/v1',
              'event_id':f'threads-{rid}',
              'timestamp':item.get('timestamp') or payload.get('captured_at') or now(),
              'observed_at':now(),
              'type':'reply.sent' if own else 'reply.observed',
              'platform':'threads',
              'actor':CHARACTER_ID if own else 'external',
              'author_handle':author or None,
              'object_id':rid,
              'parent_object_id':item.get('replied_to_id') or item.get('root_post_id') or payload.get('root_post_id'),
              'root_post_id':item.get('root_post_id') or payload.get('root_post_id'),
              'permalink':item.get('permalink'),
              'text':item.get('text'),
              'source':'AgentOS Social public-reply export',
              'execution_origin':'threads_platform_observed',
            }
            added.append(row); existing.add(rid)

        if not added:
            print('persona_git_sync=NO_CHANGE'); return 0

        with events.open('a',encoding='utf-8') as fh:
            for row in added:
                fh.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')

        run(['git','add',str(EVENTS_REL)],cwd=work)
        run(['git','-c','user.name=AgentOS Persona Sync','-c','user.email=agentos-persona-sync@users.noreply.github.com',
             'commit','-m','chore(persona): sync Sunlake Milkcat Threads events'],cwd=work)
        push=run(['git','push','origin','HEAD:main'],cwd=work,check=False)
        if push.returncode!=0:
            print('persona_git_sync=PUSH_FAILED',file=sys.stderr); return 7
        print('persona_git_sync=PASS')
        print('persona_git_sync_added='+str(len(added)))
        for row in added:
            print('persona_git_sync_event='+str(row['object_id'])+':'+str(row['type']))
        return 0
    finally:
        try: run(['git','worktree','remove','--force',str(work)],cwd=DATA_REPO,check=False)
        finally: shutil.rmtree(root,ignore_errors=True)

if __name__=='__main__':
    raise SystemExit(main())
