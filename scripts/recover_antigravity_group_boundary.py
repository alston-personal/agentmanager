#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from datetime import datetime, timezone

ROOT = Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
REPO = Path('/home/ubuntu/agentmanager')
UNIT = Path('/home/ubuntu/.config/systemd/user/agentos-antigravity-relay.service')
ACTION_UNIT = Path('/home/ubuntu/.config/systemd/user/agentos-action-relay.service')
EVIDENCE = Path('.agentos/evidence/antigravity-group-boundary-recovery.txt')


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def process_rows(pattern: str) -> list[str]:
    p = subprocess.run(['ps', '-eo', 'user,group,pid,ppid,etime,args'], text=True, capture_output=True, check=False)
    return [line for line in p.stdout.splitlines() if pattern in line and 'recover_antigravity_group_boundary.py' not in line]


def worker_has_agentos_group() -> tuple[bool, str]:
    rows = process_rows('agentos_node.antigravity_relay_worker --root /home/ubuntu/agent-data/runtime/antigravity-relay')
    details: list[str] = []
    for row in rows:
        details.append(row)
        parts = row.split()
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[2])
            status = Path(f'/proc/{pid}/status').read_text(encoding='utf-8')
        except Exception:
            continue
        gids = []
        for line in status.splitlines():
            if line.startswith('Gid:') or line.startswith('Groups:'):
                gids.extend(line.split()[1:])
        if '1005' in gids:
            return True, '\n'.join(details) + '\n' + '\n'.join(
                line for line in status.splitlines() if line.startswith(('Gid:', 'Groups:'))
            )
    return False, '\n'.join(details)


def quarantine_stale_spool(report: list[str]) -> Path:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    qroot = ROOT / 'quarantine' / f'boundary-recovery-{stamp}-{uuid.uuid4().hex[:8]}'
    q_processing = qroot / 'processing'
    q_tmp = qroot / 'receipt-tmp'
    q_processing.mkdir(parents=True, exist_ok=False)
    q_tmp.mkdir(parents=True, exist_ok=True)
    os.chmod(qroot.parent, 0o2770)
    os.chmod(qroot, 0o2770)
    os.chmod(q_processing, 0o2770)
    os.chmod(q_tmp, 0o2770)

    manifest: list[dict] = []
    for source in sorted((ROOT / 'processing').glob('relay-*.json')):
        raw = source.read_bytes()
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
        target = q_processing / source.name
        source.replace(target)
        manifest.append({
            'source': 'processing',
            'file': source.name,
            'sha256': hashlib.sha256(raw).hexdigest(),
            'created_at': data.get('created_at'),
            'project_id': data.get('project_id'),
            'goal': (data.get('canonical_ir') or {}).get('goal') if isinstance(data.get('canonical_ir'), dict) else None,
        })

    # Old failed publishers can leave ubuntu:ubuntu 0660 tmp files. The runner is
    # deliberately unable to read them. Preserve them by directory rename only;
    # reading their payload is unnecessary for safe quarantine.
    for source in sorted((ROOT / 'receipts').glob('relay-*.json.tmp')):
        st = source.stat()
        target = q_tmp / source.name
        source.replace(target)
        manifest.append({
            'source': 'receipt-tmp',
            'file': source.name,
            'sha256': None,
            'hash_status': 'unavailable-by-design-peer-owned',
            'uid': st.st_uid,
            'gid': st.st_gid,
            'mode': oct(st.st_mode & 0o777),
            'size': st.st_size,
            'mtime_ns': st.st_mtime_ns,
        })

    (qroot / 'manifest.json').write_text(json.dumps({
        'schema': 'agentos.relay-quarantine/v1',
        'created_at': now(),
        'reason': 'Stale processing capsules quarantined before restoring ubuntu agentos group boundary; no capsule was deleted or replayed.',
        'items': manifest,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report.append(f'quarantine={qroot}')
    report.append(f'quarantined_items={len(manifest)}')
    all_q = sorted((ROOT / 'quarantine').glob('boundary-recovery-*'))
    report.append('quarantine_roots=' + ','.join(str(p) for p in all_q))
    return qroot


def submit_bootstrap(report: list[str]) -> str:
    cid = 'relay-' + uuid.uuid4().hex
    payload = {
        'schema': 'agentos.antigravity-relay/v1',
        'capsule_id': cid,
        'created_at': now(),
        'project_id': 'agentmanager',
        'workspace': str(REPO),
        'executor_hint': 'antigravity',
        'instruction': (
            'Use your shell execution capability now. Execute exactly this command and do not merely describe it: '
            'cd /home/ubuntu/agentmanager && git fetch origin main && git merge --ff-only origin/main '
            '&& bash scripts/repair_antigravity_relay_user.sh . '
            'Do not perform any unrelated change. Return stdout/stderr and exit status.'
        ),
        'canonical_ir': {
            'goal': 'Restore the governed AgentOS Antigravity relay group boundary after safely quarantining stale processing work.',
            'constraints': [
                'Execute only the trusted repair script from canonical main.',
                'Do not use sudo.',
                'Do not replay quarantined capsules automatically.',
                'Do not modify unrelated projects or production services.',
            ],
        },
        'authority': {
            'source': 'agentos-node',
            'desktop_user': 'ubuntu',
            'direct_session_impersonation': False,
            'bootstrap_world_mode_inside_private_spool': True,
        },
    }
    payload['digest'] = 'sha256:' + hashlib.sha256(canonical(payload)).hexdigest()
    inbox = ROOT / 'inbox'
    tmp = inbox / f'{cid}.json.tmp'
    target = inbox / f'{cid}.json'
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    # The currently running ubuntu worker predates the agentos supplementary-group
    # grant. The spool directory itself is 2770, so making this one bootstrap file
    # world-rw does not expose it outside the private spool, but lets the old worker
    # read/write the peer-owned file long enough to run the trusted repair script.
    os.chmod(tmp, 0o666)
    tmp.replace(target)
    os.chmod(target, 0o666)
    report.append(f'bootstrap_capsule={cid}')
    report.append('bootstrap_mode=666_inside_private_2770_spool')
    return cid


def main() -> int:
    report = [f'timestamp_utc={now()}', f'identity={subprocess.getoutput("id")}']
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    try:
        for p in (ROOT, ROOT / 'inbox', ROOT / 'processing', ROOT / 'receipts'):
            if not p.is_dir():
                raise RuntimeError(f'missing relay path: {p}')

        before = sorted((ROOT / 'processing').glob('relay-*.json'))
        report.append(f'processing_before={len(before)}')
        qroot = quarantine_stale_spool(report)
        if any((ROOT / 'processing').glob('relay-*.json')):
            raise RuntimeError('processing quarantine incomplete')

        cid = submit_bootstrap(report)
        receipt = ROOT / 'receipts' / f'{cid}.json'
        deadline = time.monotonic() + 420
        unit_ok = False
        group_ok = False
        group_detail = ''
        while time.monotonic() < deadline:
            unit_text = UNIT.read_text(encoding='utf-8') if UNIT.exists() else ''
            unit_ok = '/usr/bin/sg agentos -c' in unit_text
            group_ok, group_detail = worker_has_agentos_group()
            if unit_ok and group_ok and receipt.exists():
                break
            time.sleep(2)

        report.append(f'antigravity_unit_sg_agentos={"PASS" if unit_ok else "FAIL"}')
        report.append(f'antigravity_worker_agentos_group={"PASS" if group_ok else "FAIL"}')
        report.append('worker_detail=' + group_detail.replace('\n', ' | '))
        report.append(f'bootstrap_receipt={"FOUND" if receipt.exists() else "MISSING"}')
        if receipt.exists():
            r = json.loads(receipt.read_text(encoding='utf-8'))
            report.append('bootstrap_receipt_json=' + json.dumps(r, ensure_ascii=False, sort_keys=True))
        action_text = ACTION_UNIT.read_text(encoding='utf-8') if ACTION_UNIT.exists() else ''
        report.append(f'action_relay_unit_sg_agentos={"PASS" if "/usr/bin/sg agentos -c" in action_text else "FAIL"}')
        report.append('action_relay_processes=' + ' | '.join(process_rows('agentos_node.action_relay --root /home/ubuntu/agent-data/runtime/action-relay')))
        report.append(f'processing_after={len(list((ROOT / "processing").glob("relay-*.json")))}')
        report.append(f'quarantine_preserved={"PASS" if (qroot / "manifest.json").exists() else "FAIL"}')

        ok = unit_ok and group_ok and receipt.exists()
        report.append(f'boundary_recovery={"PASS" if ok else "FAIL"}')
        return 0 if ok else 4
    except Exception as exc:
        report.append(f'boundary_recovery=ERROR {type(exc).__name__}: {exc}')
        return 3
    finally:
        EVIDENCE.write_text('\n'.join(report) + '\n', encoding='utf-8')
        print('\n'.join(report))


if __name__ == '__main__':
    raise SystemExit(main())
