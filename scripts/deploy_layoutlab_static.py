#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'web_assets/layoutlab_official.html'
TARGET = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab/index.html')


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f'missing source asset: {SOURCE}')
    data = SOURCE.read_bytes()
    if b'<title>Layout Lab | Milkcat Studio</title>' not in data or b'Analyze layout' not in data:
        raise SystemExit('source asset failed identity check')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    tmp = TARGET.with_suffix('.html.tmp')
    tmp.write_bytes(data)
    tmp.replace(TARGET)
    digest = hashlib.sha256(data).hexdigest()
    result = {
        'ok': True,
        'source': str(SOURCE),
        'target': str(TARGET),
        'bytes': len(data),
        'sha256': digest,
        'mode': 'browser-only-layoutlib-v0.1-compatible',
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
