#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_DEPLOY = ROOT / 'scripts' / 'deploy_layoutlab_static.py'
OVERLAY = ROOT / 'web_assets' / 'layoutlab-v0.7-release-fix.js'
TARGET = Path('/home/ubuntu/zeus-writer/website/dist/layout-lab')
INDEX = TARGET / 'index.html'
TARGET_OVERLAY = TARGET / OVERLAY.name
RELEASE = '0.7.8'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not BASE_DEPLOY.is_file() or not OVERLAY.is_file():
        raise SystemExit('v0.7 release source incomplete')

    base = subprocess.run(
        ['/usr/bin/python3', str(BASE_DEPLOY)],
        cwd=str(ROOT), text=True, capture_output=True, timeout=60, check=False,
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
        f'Layout Lab v{RELEASE}：2D / 3D 同屏、可編輯 Spatial IR、修正成本學習，以及 AgentOS Capability closed loop。',
    )
    text = text.replace(
        '<div class="badge">LayoutLib Browser Adapter v0.6</div>',
        f'<div class="badge" data-release="{RELEASE}">v{RELEASE}</div>',
    )
    text = text.replace(
        '<div class="compactTitle">v0.6 Learning contract</div>',
        f'<div class="compactTitle">v{RELEASE} Capability learning contract</div>',
    )

    overlay_tag = f'<script src="./layoutlab-v0.7-release-fix.js?v={RELEASE}"></script>'
    old_overlay_tag = '<script src="./layoutlab-v0.7-release-fix.js"></script>'
    bridge_tag = '<script src="./layoutlab-capability-bridge-v0.7.js"></script>'
    if old_overlay_tag in text:
        text = text.replace(old_overlay_tag, overlay_tag)
    elif overlay_tag not in text:
        if bridge_tag not in text:
            raise SystemExit('capability bridge script tag missing from base deployment')
        text = text.replace(bridge_tag, overlay_tag + '\n' + bridge_tag)
    INDEX.write_text(text, encoding='utf-8')
    INDEX.chmod(0o644)

    TARGET_OVERLAY.write_bytes(OVERLAY.read_bytes())
    TARGET_OVERLAY.chmod(0o644)

    deployed = INDEX.read_text(encoding='utf-8')
    required = [
        f'<div class="badge" data-release="{RELEASE}">v{RELEASE}</div>',
        f'Layout Lab v{RELEASE}：',
        f'v{RELEASE} Capability learning contract',
        f'layoutlab-v0.7-release-fix.js?v={RELEASE}',
        'layoutlab-capability-bridge-v0.7.js',
        'deleteWallsById',
        '刪除選取',
    ]
    missing = [x for x in required if x not in deployed]
    if missing:
        raise SystemExit(f'v0.7 release acceptance failed: {missing}')

    overlay_text = TARGET_OVERLAY.read_text(encoding='utf-8')
    overlay_required = [
        "const RELEASE='0.7.8'",
        'defaultSelection:true',
        'deleteKey:true',
        'initialWallPreview:true',
        'rightDragPan:true',
        'fixedFrameZoom:true',
        'twoDPanZoom:true',
        'durableManualEdits:true',
        'compactVersionBadge:true',
        "badge.textContent=`v${RELEASE}`",
        "button.textContent='清除手動修正'",
    ]
    overlay_missing = [x for x in overlay_required if x not in overlay_text]
    if overlay_missing:
        raise SystemExit(f'v0.7.8 overlay acceptance failed: {overlay_missing}')

    result = {
        'ok': True,
        'release': f'layoutlab-v{RELEASE}',
        'mode': 'layoutlib-v0.7-production-release',
        'index_sha256': sha(INDEX),
        'overlay_sha256': sha(TARGET_OVERLAY),
        'base_stdout': base.stdout[-4000:],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
