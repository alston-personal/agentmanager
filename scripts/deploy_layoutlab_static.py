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
    'layoutlib-editor-v0.7.js': ROOT / 'web_assets/layoutlib-editor-v0.7.js',
    'layoutlab-editor-ui-v0.7.js': ROOT / 'web_assets/layoutlab-editor-ui-v0.7.js',
    'layoutlab-capability-bridge-v0.7.js': ROOT / 'web_assets/layoutlab-capability-bridge-v0.7.js',
}
TARGET_DIR = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab')


def _identity(name: str, data: bytes) -> None:
    if name == 'index.html':
        required = [b'<title>Layout Lab | Milkcat Studio</title>', b'LayoutLib Browser Adapter v0.6', b'layoutlib.profile.samples.v1', b'previewEraseStrokePx']
        if not all(x in data for x in required):
            raise SystemExit('html source asset failed base identity check')
    elif name == 'layoutlib-browser-v0.5.js':
        required = [b'LayoutLib Browser Adapter v0.6.0', b"version:'0.6.0'", b'previewEraseStrokePx', b'extractProfileFeatures', b'predictProfileParameters', b'makeLearningObservation', b'replayEdits']
        if not all(x in data for x in required):
            raise SystemExit('browser parser core failed identity check')
    elif name == 'layoutlib-editor-v0.7.js':
        required = [b'LayoutLib Editor Semantics v0.7.0', b'deleteWallsById', b'moveWallPx', b'replayCorrections', b'matchWallByEvidence', b'createCorrectionSession']
        if not all(x in data for x in required):
            raise SystemExit('LayoutLib editor semantics failed identity check')
    elif name == 'layoutlab-editor-ui-v0.7.js':
        required = [b'Layout Lab editor UI adapter v0.7.0', b'LayoutLibEditor', b'deleteSelected', b'selectWallNearPx']
        if not all(x in data for x in required):
            raise SystemExit('Layout Lab editor UI adapter failed identity check')
    elif name == 'layoutlab-capability-bridge-v0.7.js':
        required = [b'Layout Lab -> AgentOS Capability Experience Bridge v0.7.0', b'finishModel', b'agentos.capability-experience/v1', b'applyCanonicalPolicy', b'layoutlib.capability.pending.v1']
        if not all(x in data for x in required):
            raise SystemExit('capability bridge asset failed v0.7 identity check')


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(TARGET_DIR, 0o755)
    artifacts = {}
    for name, source in SOURCES.items():
        if not source.is_file():
            raise SystemExit(f'missing source asset: {source}')
        data = source.read_bytes()
        _identity(name, data)
        if name == 'index.html':
            text = data.decode('utf-8')
            tags = [
                '<script src="./layoutlib-editor-v0.7.js"></script>',
                '<script src="./layoutlab-editor-ui-v0.7.js"></script>',
                '<script src="./layoutlab-capability-bridge-v0.7.js"></script>',
            ]
            for tag in tags:
                if tag not in text:
                    text = text.replace('</body>', tag + '\n</body>')
            data = text.encode('utf-8')
        target = TARGET_DIR / name
        tmp = target.with_suffix(target.suffix + '.tmp')
        tmp.write_bytes(data)
        os.chmod(tmp, 0o644)
        tmp.replace(target)
        os.chmod(target, 0o644)
        artifacts[name] = {'source': str(source), 'target': str(target), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    print(json.dumps({'ok': True, 'directory': str(TARGET_DIR), 'directory_mode': '0755', 'file_mode': '0644', 'mode': 'layoutlib-v0.7-library-backed-demo', 'artifacts': artifacts}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
