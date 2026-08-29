#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUNTIME = '/home/ubuntu/.local/share/agentos/runtime-vnext'
RELAY = Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
BASE = Path('/home/ubuntu/agent-data/runtime/vendor-reputation')
INPUT = BASE / 'threads-DcWVvpwGTSh-normalized-replies.json'
OUTPUT = BASE / 'threads-DcWVvpwGTSh-vendor-candidates.json'
BATCH_DIR = BASE / 'classification-batches'
BATCH_SIZE = 5

sys.path.insert(0, RUNTIME)
from agentos_node.antigravity_relay import AntigravityRelayClient

if not INPUT.is_file():
    raise SystemExit(f'missing input: {INPUT}')
source = json.loads(INPUT.read_text(encoding='utf-8'))
rows = source.get('normalized_replies') or []
if not rows:
    raise SystemExit('normalized reply input is empty')

BATCH_DIR.mkdir(parents=True, exist_ok=True)
os.chmod(BATCH_DIR, 0o700)
client = AntigravityRelayClient(str(RELAY))
all_evidence = []
receipts = []

for start in range(0, len(rows), BATCH_SIZE):
    batch_no = start // BATCH_SIZE + 1
    batch_rows = rows[start:start + BATCH_SIZE]
    batch_in = BATCH_DIR / f'batch-{batch_no:02d}-input.json'
    batch_out = BATCH_DIR / f'batch-{batch_no:02d}-output.json'
    batch_in.write_text(json.dumps({
        'schema': 'agentos.vendor-threads-normalized-batch/v1',
        'source_thread': source.get('source_thread'),
        'normalized_replies': batch_rows,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.chmod(batch_in, 0o600)
    if batch_out.exists():
        batch_out.unlink()

    instruction = f'''Classify ONLY the small normalized Threads evidence batch at {batch_in} for the Vendor Reputation Index and write valid JSON to {batch_out}.

This is evidence extraction only. Do NOT publish anything and do NOT assign star ratings.
Output exactly this conceptual structure:
{{"schema":"agentos.vendor-evidence-classification-batch/v1","evidence":[{{"evidence_id":"preserve exact input id","source_url":"preserve exact input permalink","source_author":"preserve exact input author","vendor_mentions":[{{"vendor_name":"only when explicit in evidence","aliases":[],"service_category":"water/electricity/aircon/cleaning/renovation/moving/appliance-repair/other or null","region":"only when explicit or strongly grounded, else null","signal":"positive|negative|mixed|neutral|unclear","confidence":0.0,"reason":"short paraphrase only"}}],"review_status":"pending"}}]}}
Rules: never invent vendor identity/region; if no identifiable vendor use vendor_mentions=[]; never emit rating/stars/score fields; keep all records pending; omit original_text from output; preserve provenance exactly; chmod output 0600; do not print vendor names/authors/reply text to stdout or stderr. Validate JSON before exit.'''

    capsule = client.submit(
        project_id='vendor-reputation',
        canonical_ir={
            'goal': f'Classify vendor evidence batch {batch_no} of {(len(rows)+BATCH_SIZE-1)//BATCH_SIZE}.',
            'acceptance': ['preserve provenance','no inferred star ratings','all records pending review','valid private JSON'],
            'constraints': ['private Oracle evidence only','no publication','no fabricated vendor identity or region'],
        },
        instruction=instruction,
        workspace=str(BASE),
    )
    capsule_id = capsule['capsule_id']
    receipt = RELAY / 'receipts' / f'{capsule_id}.json'
    for _ in range(210):
        if receipt.is_file():
            break
        time.sleep(1)
    else:
        raise SystemExit(f'batch {batch_no} receipt timeout')
    r = json.loads(receipt.read_text(encoding='utf-8'))
    receipts.append({'batch': batch_no, 'capsule_id': capsule_id, 'ok': r.get('ok'), 'timed_out': r.get('timed_out'), 'returncode': r.get('returncode')})
    if r.get('ok') is not True:
        raise SystemExit(f'AgentOS classifier failed on batch {batch_no}: timeout={r.get("timed_out")} returncode={r.get("returncode")}')
    if not batch_out.is_file():
        raise SystemExit(f'batch {batch_no} output missing')
    data = json.loads(batch_out.read_text(encoding='utf-8'))
    ev = data.get('evidence') or []
    expected_ids = {x.get('evidence_id') for x in batch_rows}
    actual_ids = {x.get('evidence_id') for x in ev}
    if actual_ids != expected_ids:
        raise SystemExit(f'batch {batch_no} provenance mismatch')
    for e in ev:
        if e.get('review_status') != 'pending' or not e.get('source_url'):
            raise SystemExit(f'batch {batch_no} invalid evidence state')
        for m in e.get('vendor_mentions') or []:
            if {'rating','stars','score'} & set(m):
                raise SystemExit(f'batch {batch_no} forbidden rating field')
            if not m.get('vendor_name') or m.get('signal') not in {'positive','negative','mixed','neutral','unclear'}:
                raise SystemExit(f'batch {batch_no} invalid mention')
    os.chmod(batch_out, 0o600)
    all_evidence.extend(ev)

if len(all_evidence) != len(rows):
    raise SystemExit('merged evidence count mismatch')
merged = {
    'schema': 'agentos.vendor-evidence-classification/v1',
    'source_thread': source.get('source_thread'),
    'classified_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z'),
    'evidence': all_evidence,
}
OUTPUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
os.chmod(OUTPUT, 0o600)
mentions = [m for e in all_evidence for m in (e.get('vendor_mentions') or [])]
vendors = {str(m.get('vendor_name')).strip().casefold() for m in mentions if m.get('vendor_name')}
summary = {
    'schema': 'agentos.vendor-evidence-classification-summary/v2',
    'ok': True,
    'source_thread': merged.get('source_thread'),
    'input_evidence_records': len(rows),
    'batches': len(receipts),
    'successful_batches': sum(1 for x in receipts if x['ok']),
    'evidence_records': len(all_evidence),
    'vendor_mentions': len(mentions),
    'distinct_vendor_name_keys': len(vendors),
    'pending_review_records': sum(1 for e in all_evidence if e.get('review_status') == 'pending'),
    'positive_mentions': sum(1 for m in mentions if m.get('signal') == 'positive'),
    'negative_mentions': sum(1 for m in mentions if m.get('signal') == 'negative'),
    'mixed_mentions': sum(1 for m in mentions if m.get('signal') == 'mixed'),
    'neutral_or_unclear_mentions': sum(1 for m in mentions if m.get('signal') in {'neutral','unclear'}),
    'private_output_path': str(OUTPUT),
    'raw_comment_text_committed': False,
    'vendor_names_committed': False,
    'publication_performed': False,
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
