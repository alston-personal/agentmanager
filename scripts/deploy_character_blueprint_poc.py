#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'web_assets' / 'character-blueprint-poc.html'
TARGET = Path('/home/ubuntu/zeus-writer/website/dist/poc/character-blueprint')
MARKERS = [
    'data-version="0.4.0"',
    'character-blueprint-ir/v0.4',
    'threeDProxy:true',
    'interactivePartLinking:true',
    '3D Blueprint',
    'OrbitControls',
    'llm_tokens: 0',
]
FORBIDDEN_FALLBACK = ['Milkcat Studio Portal', 'SERIALS', '連載作品']


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(text: str) -> None:
    missing = [m for m in MARKERS if m not in text]
    if missing:
        raise SystemExit(f'character blueprint source invalid: missing={missing}')
    if all(x in text for x in FORBIDDEN_FALLBACK):
        raise SystemExit('character blueprint source unexpectedly contains Studio fallback identity')


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f'missing source: {SOURCE}')
    validate(SOURCE.read_text(encoding='utf-8'))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.parent.chmod(0o755)
    tmp: Path | None = Path(tempfile.mkdtemp(prefix='.character-blueprint-', dir=str(TARGET.parent)))
    tmp.chmod(0o755)
    try:
        index = tmp / 'index.html'
        shutil.copy2(SOURCE, index)
        index.chmod(0o644)
        validate(index.read_text(encoding='utf-8'))
        backup = TARGET.with_name(TARGET.name + '.previous')
        if backup.exists(): shutil.rmtree(backup)
        if TARGET.exists(): TARGET.rename(backup)
        tmp.rename(TARGET)
        TARGET.chmod(0o755)
        tmp = None
        if backup.exists(): shutil.rmtree(backup)
    finally:
        if tmp is not None and tmp.exists(): shutil.rmtree(tmp)

    deployed = TARGET / 'index.html'
    validate(deployed.read_text(encoding='utf-8'))
    print(json.dumps({
        'ok': True,
        'release': 'character-blueprint-poc-v0.4',
        'target': str(TARGET),
        'public_path': '/poc/character-blueprint/',
        'marker': 'character-blueprint-poc/v0.4.0',
        'three_d_proxy': True,
        'interactive_part_linking': True,
        'llm_tokens': 0,
        'sha256': digest(deployed),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
