#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

RUNTIME = '/home/ubuntu/.local/share/agentos/runtime-vnext'
RELAY = Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
INPUT = Path('/home/ubuntu/agent-data/runtime/vendor-reputation/threads-DcWVvpwGTSh-normalized-replies.json')
OUTPUT = Path('/home/ubuntu/agent-data/runtime/vendor-reputation/threads-DcWVvpwGTSh-vendor-candidates.json')
SUMMARY = Path('.agentos/evidence/threads-vendor-classification-summary.json')

sys.path.insert(0, RUNTIME)
from agentos_node.antigravity_relay import AntigravityRelayClient

if not INPUT.is_file():
    raise SystemExit(f'missing input: {INPUT}')

client = AntigravityRelayClient(str(RELAY))
instruction = f'''Read the normalized public Threads reply evidence at {INPUT} and classify it for the Vendor Reputation Index.

This is evidence extraction, NOT publication and NOT rating assignment. Write valid JSON to {OUTPUT}. Do not print raw reply text, vendor names, authors, tokens, or private evidence to stdout/stderr.

Output schema:
{{
  "schema": "agentos.vendor-evidence-classification/v1",
  "source_thread": "https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh",
  "classified_at": "ISO8601",
  "evidence": [
    {{
      "evidence_id": "preserve input evidence_id",
      "source_url": "preserve exact Threads reply permalink",
      "source_author": "preserve input author",
      "vendor_mentions": [
        {{
          "vendor_name": "only if explicitly supported by the reply text",
          "aliases": [],
          "service_category": "water/electricity/aircon/cleaning/renovation/moving/appliance-repair/other or null",
          "region": "only if explicit or strongly grounded, otherwise null",
          "signal": "positive|negative|mixed|neutral|unclear",
          "confidence": 0.0,
          "reason": "short paraphrase; no long quote"
        }}
      ],
      "review_status": "pending"
    }}
  ]
}}

Rules:
1. Never invent a vendor name. If no vendor is identifiable, vendor_mentions must be [].
2. Never convert prose or recommendation language into a star rating. Do not output rating/stars/score fields.
3. Preserve exact evidence_id, source_url, and source_author from input.
4. Do not merge similar vendor names unless evidence clearly supports aliases.
5. Do not infer region from user profile or unrelated context.
6. Signal describes only that evidence item, not an overall vendor score.
7. Every evidence record remains review_status=pending. Publish nothing.
8. Do not include original_text in the classification output; it remains in the private input receipt.
9. chmod output 0600 if possible.
10. stdout must contain only a compact summary line without vendor names/authors/text.
Validate JSON before finishing.'''

capsule = client.submit(
    project_id='vendor-reputation',
    canonical_ir={
        'goal': 'Classify real public Threads replies into reviewable vendor evidence without inventing ratings.',
        'acceptance': [
            'input provenance remains linked',
            'no star ratings inferred from prose',
            'all evidence remains pending review',
            'raw reply text stays private',
            'classification JSON is valid',
        ],
        'constraints': [
            'read Oracle private normalized evidence',
            'write only Oracle private classification output',
            'no publication',
            'no fabricated vendor identity or region',
        ],
    },
    instruction=instruction,
    workspace='/home/ubuntu/agentmanager',
)
capsule_id = capsule['capsule_id']
receipt = RELAY / 'receipts' / f'{capsule_id}.json'
for _ in range(900):
    if receipt.is_file():
        break
    time.sleep(1)
else:
    raise SystemExit('classification receipt timeout')

r = json.loads(receipt.read_text(encoding='utf-8'))
if r.get('ok') is not True:
    raise SystemExit('AgentOS classification executor failed')
if not OUTPUT.is_file():
    raise SystemExit('classification output missing')

data = json.loads(OUTPUT.read_text(encoding='utf-8'))
ev = data.get('evidence') or []
mentions = []
for e in ev:
    if e.get('review_status') != 'pending':
        raise SystemExit('non-pending evidence detected')
    if not e.get('evidence_id') or not e.get('source_url'):
        raise SystemExit('provenance missing')
    for m in e.get('vendor_mentions') or []:
        forbidden = {'rating', 'stars', 'score'} & set(m)
        if forbidden:
            raise SystemExit('forbidden inferred rating field present')
        if not m.get('vendor_name'):
            raise SystemExit('empty vendor name')
        if m.get('signal') not in {'positive','negative','mixed','neutral','unclear'}:
            raise SystemExit('invalid signal')
        mentions.append(m)

vendors = {str(m.get('vendor_name')).strip().casefold() for m in mentions if m.get('vendor_name')}
os.chmod(OUTPUT, 0o600)
summary = {
    'schema': 'agentos.vendor-evidence-classification-summary/v1',
    'ok': True,
    'source_thread': data.get('source_thread'),
    'evidence_records': len(ev),
    'vendor_mentions': len(mentions),
    'distinct_vendor_name_keys': len(vendors),
    'pending_review_records': sum(1 for e in ev if e.get('review_status') == 'pending'),
    'positive_mentions': sum(1 for m in mentions if m.get('signal') == 'positive'),
    'negative_mentions': sum(1 for m in mentions if m.get('signal') == 'negative'),
    'mixed_mentions': sum(1 for m in mentions if m.get('signal') == 'mixed'),
    'neutral_or_unclear_mentions': sum(1 for m in mentions if m.get('signal') in {'neutral','unclear'}),
    'private_output_path': str(OUTPUT),
    'raw_comment_text_committed': False,
    'vendor_names_committed': False,
    'publication_performed': False,
}
SUMMARY.parent.mkdir(parents=True, exist_ok=True)
SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('classification=PASS evidence=%d mentions=%d vendors=%d pending=%d' % (
    summary['evidence_records'], summary['vendor_mentions'], summary['distinct_vendor_name_keys'], summary['pending_review_records']))
