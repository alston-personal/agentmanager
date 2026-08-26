#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'index.html': ROOT / 'web_assets/layoutlab_official.html',
    'layoutlib-browser-v0.3.js': ROOT / 'web_assets/layoutlib-browser-v0.3.js',
}
TARGET_DIR = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab')


def _identity(name: str, data: bytes) -> None:
    if name == 'index.html':
        if b'<title>Layout Lab | Milkcat Studio</title>' not in data or b'LayoutLib Browser Adapter v0.4' not in data:
            raise SystemExit('html source asset failed identity check')
    elif name.endswith('.js'):
        if b'LayoutLib Browser Adapter v0.4.1' not in data or b'worldToSourcePx' not in data or b'createScaleCalibration' not in data:
            raise SystemExit('browser library asset failed identity check')


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(TARGET_DIR, 0o755)
    artifacts = {}
    for name, source in SOURCES.items():
        if not source.is_file():
            raise SystemExit(f'missing source asset: {source}')
        data = source.read_bytes()
        _identity(name, data)
        target = TARGET_DIR / name
        tmp = target.with_suffix(target.suffix + '.tmp')
        tmp.write_bytes(data)
        os.chmod(tmp, 0o644)
        tmp.replace(target)
        os.chmod(target, 0o644)
        artifacts[name] = {
            'source': str(source),
            'target': str(target),
            'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(),
        }
    result = {
        'ok': True,
        'directory': str(TARGET_DIR),
        'directory_mode': '0755',
        'file_mode': '0644',
        'mode': 'layoutlib-v0.4.1-reference-app',
        'artifacts': artifacts,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
