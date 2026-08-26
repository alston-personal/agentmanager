#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'index.html': ROOT / 'web_assets/layoutlab_v0_5.html',
    'layoutlib-browser-v0.5.js': ROOT / 'web_assets/layoutlib-browser-v0.5.js',
}
TARGET_DIR = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab')


def _identity(name: str, data: bytes) -> None:
    if name == 'index.html':
        required = [
            b'<title>Layout Lab | Milkcat Studio</title>',
            b'LayoutLib Browser Adapter v0.6',
            b'3D \xe5\x8d\xb3\xe6\x99\x82\xe5\xb0\x8d\xe7\x85\xa7',
            b'layoutlib.profile.samples.v1',
            b'previewEraseStrokePx',
        ]
        if not all(x in data for x in required):
            raise SystemExit('html source asset failed v0.6 identity check')
    elif name.endswith('.js'):
        required = [
            b'LayoutLib Browser Adapter v0.6.0',
            b"version:'0.6.0'",
            b'previewEraseStrokePx',
            b'extractProfileFeatures',
            b'predictProfileParameters',
            b'makeLearningObservation',
            b'replayEdits',
        ]
        if not all(x in data for x in required):
            raise SystemExit('browser library asset failed v0.6 identity check')


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
    print(json.dumps({
        'ok': True,
        'directory': str(TARGET_DIR),
        'directory_mode': '0755',
        'file_mode': '0644',
        'mode': 'layoutlib-v0.6-generalized-profile-learning',
        'artifacts': artifacts,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
