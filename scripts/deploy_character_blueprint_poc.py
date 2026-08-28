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
    '"llm_tokens":0',
]
FORBIDDEN_FALLBACK = ['Milkcat Studio Portal', 'SERIALS', '連載作品']
THREE_DIRECT = "import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.179.1/build/three.module.js';"
ORBIT_DIRECT = "import {OrbitControls} from 'https://cdn.jsdelivr.net/npm/three@0.179.1/examples/jsm/controls/OrbitControls.js';"
IMPORT_MAP = '''<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.179.1/build/three.module.js","three/addons/":"https://cdn.jsdelivr.net/npm/three@0.179.1/examples/jsm/"}}
</script>'''
THREE_MAPPED = "import * as THREE from 'three';"
ORBIT_MAPPED = "import {OrbitControls} from 'three/addons/controls/OrbitControls.js';"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(text: str) -> None:
    missing = [m for m in MARKERS if m not in text]
    if missing:
        raise SystemExit(f'character blueprint source invalid: missing={missing}')
    if all(x in text for x in FORBIDDEN_FALLBACK):
        raise SystemExit('character blueprint source unexpectedly contains Studio fallback identity')


def make_browser_safe(text: str) -> str:
    old = f'<script type="module">\n{THREE_DIRECT}\n{ORBIT_DIRECT}'
    new = f'{IMPORT_MAP}\n<script type="module">\n{THREE_MAPPED}\n{ORBIT_MAPPED}'
    if old not in text:
        raise SystemExit('character blueprint deploy transform failed: expected Three.js direct imports not found')
    text = text.replace(old, new, 1)
    required = ['type="importmap"', '"three/addons/"', "from 'three'", "from 'three/addons/controls/OrbitControls.js'"]
    missing = [m for m in required if m not in text]
    if missing:
        raise SystemExit(f'character blueprint browser import transform invalid: missing={missing}')
    return text


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f'missing source: {SOURCE}')
    source_text = SOURCE.read_text(encoding='utf-8')
    validate(source_text)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.parent.chmod(0o755)
    tmp: Path | None = Path(tempfile.mkdtemp(prefix='.character-blueprint-', dir=str(TARGET.parent)))
    tmp.chmod(0o755)
    try:
        index = tmp / 'index.html'
        index.write_text(make_browser_safe(source_text), encoding='utf-8')
        index.chmod(0o644)
        deployed_text = index.read_text(encoding='utf-8')
        validate(deployed_text)
        if 'type="importmap"' not in deployed_text or "from 'three/addons/controls/OrbitControls.js'" not in deployed_text:
            raise SystemExit('character blueprint browser import wiring missing after transform')
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
    final_text = deployed.read_text(encoding='utf-8')
    validate(final_text)
    if 'type="importmap"' not in final_text:
        raise SystemExit('character blueprint public artifact missing import map')
    print(json.dumps({
        'ok': True,
        'release': 'character-blueprint-poc-v0.4',
        'target': str(TARGET),
        'public_path': '/poc/character-blueprint/',
        'marker': 'character-blueprint-poc/v0.4.0',
        'three_d_proxy': True,
        'interactive_part_linking': True,
        'browser_import_map': True,
        'llm_tokens': 0,
        'sha256': digest(deployed),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
