#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_DEPLOY = ROOT / 'scripts' / 'deploy_layoutlab_static.py'
OVERLAY = ROOT / 'web_assets' / 'layoutlab-v0.7-release-fix.js'
TARGET = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab')
INDEX = TARGET / 'index.html'
TARGET_OVERLAY = TARGET / OVERLAY.name
RELEASE = '0.7.9'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not BASE_DEPLOY.is_file() or not OVERLAY.is_file():
        raise SystemExit('v0.7 release source incomplete')

    env = os.environ.copy()
    env['LAYOUTLAB_RELEASE_BASE_DEPLOY'] = '1'
    base = subprocess.run(
        ['/usr/bin/python3', str(BASE_DEPLOY)],
        cwd=str(ROOT), text=True, capture_output=True, timeout=60, check=False, env=env,
    )
    if base.returncode != 0:
        print(base.stdout, end='')
        print(base.stderr, end='')
        raise SystemExit(base.returncode)
    if not INDEX.is_file():
        raise SystemExit('base deployment did not produce Layout Lab index')

    text = INDEX.read_text(encoding='utf-8')
    text = text.replace(
        'LayoutLib v0.6：2D / 3D 同屏、即時擦除反白、Draft/Committed 分離，以及從圖面特徵抽象學習 parser profile；不是記住單一圖片。',
        'Floor Plan → Spatial IR → 3D',
    )
    text = text.replace(
        '<div class="badge">LayoutLib Browser Adapter v0.6</div>',
        f'<div class="badge" data-release="{RELEASE}">v{RELEASE}</div>',
    )
    text = text.replace(
        '<div class="compactTitle">v0.6 Learning contract</div>',
        '<div class="compactTitle">Semantic IR</div>',
    )
    for asset in ['layoutlib-spatial-semantics-v0.1.js','layoutlib-editor-v0.7.js','layoutlab-editor-ui-v0.7.js']:
        text = text.replace(f'<script src="./{asset}"></script>', f'<script src="./{asset}?v={RELEASE}"></script>')
    overlay_tag = f'<script src="./layoutlab-v0.7-release-fix.js?v={RELEASE}"></script>'
    bridge_tag = '<script src="./layoutlab-capability-bridge-v0.7.js"></script>'
    if overlay_tag not in text:
        if bridge_tag not in text:
            raise SystemExit('capability bridge script tag missing from base deployment')
        # Historical bridge mutates the header identity to the old v0.7 closed-loop label.
        # Keep the immutable bridge untouched; run the release overlay after it so v0.7.9
        # is the final presentation authority.
        text = text.replace(bridge_tag, bridge_tag + '\n' + overlay_tag)
    INDEX.write_text(text, encoding='utf-8')
    INDEX.chmod(0o644)

    TARGET_OVERLAY.write_bytes(OVERLAY.read_bytes())
    TARGET_OVERLAY.chmod(0o644)

    deployed = INDEX.read_text(encoding='utf-8')
    required = [
        f'<div class="badge" data-release="{RELEASE}">v{RELEASE}</div>',
        'Floor Plan → Spatial IR → 3D',
        '<div class="compactTitle">Semantic IR</div>',
        f'layoutlib-spatial-semantics-v0.1.js?v={RELEASE}',
        f'layoutlib-editor-v0.7.js?v={RELEASE}',
        f'layoutlab-editor-ui-v0.7.js?v={RELEASE}',
        f'layoutlab-v0.7-release-fix.js?v={RELEASE}',
        'layoutlab-capability-bridge-v0.7.js',
    ]
    missing = [x for x in required if x not in deployed]
    forbidden = ['AgentOS closed loop', 'Capability learning contract']
    bad = [x for x in forbidden if x in deployed]
    wrong_order = deployed.find(bridge_tag) < 0 or deployed.find(overlay_tag) < 0 or deployed.find(bridge_tag) > deployed.find(overlay_tag)
    if missing or bad or wrong_order:
        raise SystemExit(f'v0.7 release acceptance failed: missing={missing} forbidden={bad} bridge_before_overlay={not wrong_order}')

    semantic = TARGET / 'layoutlib-spatial-semantics-v0.1.js'
    if not semantic.is_file():
        raise SystemExit('semantic MVP asset missing after deployment')
    semantic_text = semantic.read_text(encoding='utf-8')
    semantic_required = ['LayoutLib Spatial Semantics v0.1.0','candidateOpenings','classifyOpening','segmentRooms','token_cost:0']
    semantic_missing = [x for x in semantic_required if x not in semantic_text]
    if semantic_missing:
        raise SystemExit(f'semantic MVP acceptance failed: {semantic_missing}')

    overlay_text = TARGET_OVERLAY.read_text(encoding='utf-8')
    overlay_required = [
        "const RELEASE='0.7.9'", 'uiOnly:true', 'deleteKey:true', 'rightDragPan:true',
        'fixedFrameZoom:true', 'twoDPanZoom:true', 'compactVersionBadge:true',
        "badge.textContent=`v${RELEASE}`", "button.textContent='清除手動修正'",
    ]
    overlay_forbidden = ['deleteWallsById=', 'function removeByEvidence', 'MANUAL_OPS=', 'replayEdits=']
    overlay_missing = [x for x in overlay_required if x not in overlay_text]
    overlay_bad = [x for x in overlay_forbidden if x in overlay_text]
    if overlay_missing or overlay_bad:
        raise SystemExit(f'v0.7.9 UI-only overlay acceptance failed: missing={overlay_missing} forbidden={overlay_bad}')

    result = {
        'ok': True,
        'release': f'layoutlab-v{RELEASE}',
        'mode': 'layoutlib-v0.7-library-backed-demo+semantic-mvp',
        'semantic_mvp': True,
        'authoritative_publisher': True,
        'index_sha256': sha(INDEX),
        'semantic_sha256': sha(semantic),
        'overlay_sha256': sha(TARGET_OVERLAY),
        'base_stdout': base.stdout[-4000:],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
