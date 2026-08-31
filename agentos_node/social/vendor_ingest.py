from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .threads import ThreadsCapability


@dataclass(frozen=True)
class VendorEvidence:
    source: str
    platform: str
    object_id: str
    author: str | None
    observed_at: str | None
    permalink: str | None
    text: str
    evidence_type: str = 'community_comment'
    status: str = 'unreviewed'


def collect_thread_replies(thread_id: str, *, source_url: str | None = None, limit: int = 100,
                           credential_ref: str = 'threads/default') -> dict[str, Any]:
    """Collect raw Threads replies as provenance-preserving vendor evidence.

    This function intentionally does not infer vendor names or sentiment. Extraction and
    scoring happen in a separate review stage so a mention/question cannot silently become
    a positive or negative rating.
    """
    capability = ThreadsCapability(credential_ref=credential_ref)
    receipt = capability.replies_read(thread_id, limit=limit)
    if not receipt.ok:
        return {
            'schema': 'milkcat.vendor-evidence-batch/v0.1',
            'ok': False,
            'source_url': source_url,
            'thread_id': thread_id,
            'receipt': receipt.to_dict(),
            'evidence': [],
        }

    replies = receipt.result.get('replies') if isinstance(receipt.result, dict) else []
    evidence = []
    for item in replies if isinstance(replies, list) else []:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        evidence.append(VendorEvidence(
            source=source_url or receipt.permalink or f'threads:{thread_id}',
            platform='threads',
            object_id=str(item.get('id') or ''),
            author=item.get('username'),
            observed_at=item.get('timestamp'),
            permalink=item.get('permalink'),
            text=text,
        ))

    return {
        'schema': 'milkcat.vendor-evidence-batch/v0.1',
        'ok': True,
        'source_url': source_url,
        'thread_id': thread_id,
        'receipt': receipt.to_dict(),
        'evidence_count': len(evidence),
        'evidence': [asdict(item) for item in evidence],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Collect Threads replies for Vendor Reputation review')
    parser.add_argument('--thread-id', required=True, help='Threads Graph object id; never infer from a public URL slug')
    parser.add_argument('--source-url')
    parser.add_argument('--credential', default='threads/default')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--output')
    args = parser.parse_args(argv)

    batch = collect_thread_replies(
        args.thread_id,
        source_url=args.source_url,
        limit=args.limit,
        credential_ref=args.credential,
    )
    rendered = json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + '\n', encoding='utf-8')
    else:
        print(rendered)
    return 0 if batch.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
