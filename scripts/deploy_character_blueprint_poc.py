#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
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

STABLE_PROXY_FUNCTIONS = r'''function coverage(l){const ok=(i,t=.4)=>{const p=l[i];return !!p&&(p.visibility??0)>=t&&p.x>=-.08&&p.x<=1.08&&p.y>=-.08&&p.y<=1.08};return ok(27)&&ok(28)?'full_body':ok(25)&&ok(26)?'three_quarter':'upper_body'}
function reliablePoint(l,i,t=.38){const p=l[i];return !!p&&(p.visibility??0)>=t&&p.x>=-.12&&p.x<=1.12&&p.y>=-.12&&p.y<=1.12}
function rebuild3D(l){init3D();if(root)scene.remove(root);root=new THREE.Group();scene.add(root);meshParts=[];
 const shL=v(l,11),shR=v(l,12),shoulder=mean(shL,shR),sw=Math.max(.55,shL.distanceTo(shR)),cov=coverage(l);
 let hip,torsoLen;
 if(cov!=='upper_body'&&reliablePoint(l,23,.42)&&reliablePoint(l,24,.42)){const rawHip=mean(v(l,23),v(l,24)),d=rawHip.clone().sub(shoulder),ratio=d.length()/sw;if(d.y<-.15&&ratio>.55&&ratio<2.2){hip=rawHip;torsoLen=d.length()}else{torsoLen=sw*1.18;hip=shoulder.clone().add(new THREE.Vector3(0,-torsoLen,0))}}
 else{torsoLen=sw*1.18;hip=shoulder.clone().add(new THREE.Vector3(0,-torsoLen,0))}
 const torsoAxis=hip.clone().sub(shoulder).normalize(),torsoCenter=mean(shoulder,hip);
 let headCenter=shoulder.clone().add(new THREE.Vector3(0,sw*.82,0));
 if(reliablePoint(l,7,.28)&&reliablePoint(l,8,.28)){const earMid=mean(v(l,7),v(l,8)),delta=earMid.clone().sub(shoulder);if(delta.y>.1&&delta.length()<sw*1.6)headCenter=earMid}
 else if(reliablePoint(l,0,.3)){const nose=v(l,0),delta=nose.clone().sub(shoulder);if(delta.y>.1&&delta.length()<sw*1.6)headCenter=nose.clone().add(new THREE.Vector3(0,sw*.12,0))}
 const headR=Math.max(.24,sw*.31);
 addMesh(new THREE.SphereGeometry(1,28,20),'head',headCenter,new THREE.Vector3(headR*.82,headR,headR*.72));
 addMesh(new THREE.SphereGeometry(1,24,18),'hair',headCenter.clone().add(new THREE.Vector3(0,headR*.12,-headR*.04)),new THREE.Vector3(headR*.98,headR*1.12,headR*.88));
 const bodyR=Math.max(.18,sw*.24),bodyLen=Math.max(.08,torsoLen-bodyR*2),torso=addMesh(new THREE.CapsuleGeometry(bodyR,bodyLen,8,18),'body',torsoCenter,new THREE.Vector3(1,1,.72));torso.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),torsoAxis);
 const garmentR=Math.max(.21,sw*.285),garmentLen=Math.max(.08,torsoLen-garmentR*1.7),garment=addMesh(new THREE.CapsuleGeometry(garmentR,garmentLen,8,18),'garment',torsoCenter.clone().add(new THREE.Vector3(0,-sw*.03,0)),new THREE.Vector3(1.04,1,.84));garment.quaternion.copy(torso.quaternion);
 const armChains=[['left_arm',11,13,15],['right_arm',12,14,16]];for(const [part,a,b,c] of armChains){if(!reliablePoint(l,b,.22))continue;const A=v(l,a),B=v(l,b);cylinderBetween(A,B,Math.max(.055,sw*.095),part);if(reliablePoint(l,c,.2))cylinderBetween(B,v(l,c),Math.max(.05,sw*.085),part)}
 if(cov!=='upper_body'){const legChains=[['left_leg',23,25,27],['right_leg',24,26,28]];for(const [part,a,b,c] of legChains){if(!reliablePoint(l,a,.35)||!reliablePoint(l,b,.3))continue;const A=v(l,a),B=v(l,b);cylinderBetween(A,B,Math.max(.07,sw*.12),part);if(reliablePoint(l,c,.28))cylinderBetween(B,v(l,c),Math.max(.06,sw*.1),part)}}
 root.userData.proxyBodyFrame='visibility-gated-v0.4.1';viewerEmpty.style.display='none';fitCamera();selectPart(selected)}'''


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


def make_proxy_stable(text: str) -> str:
    pattern = re.compile(r"function coverage\(l\)\{.*?\}\nfunction buildIR\(l\)", re.S)
    m = pattern.search(text)
    if not m:
        raise SystemExit('character blueprint geometry transform failed: coverage/buildIR boundary missing')
    # Preserve buildIR; replace coverage and inject reliability helper.
    prefix = STABLE_PROXY_FUNCTIONS.split('function rebuild3D', 1)[0]
    text = text[:m.start()] + prefix + 'function buildIR(l)' + text[m.end():]
    rebuild_pattern = re.compile(r"function rebuild3D\(l\)\{.*?viewerEmpty\.style\.display='none';fitCamera\(\);selectPart\(selected\)\}", re.S)
    rebuild = 'function rebuild3D' + STABLE_PROXY_FUNCTIONS.split('function rebuild3D', 1)[1]
    text, count = rebuild_pattern.subn(rebuild, text, count=1)
    if count != 1:
        raise SystemExit(f'character blueprint geometry transform failed: rebuild matches={count}')
    text = text.replace('POC v0.4 · browser-local', 'POC v0.4.1 · browser-local', 1)
    text = text.replace('<title>Character Blueprint POC v0.4</title>', '<title>Character Blueprint POC v0.4.1</title>', 1)
    text = text.replace('meta name="character-blueprint-poc" content="v0.4.0"', 'meta name="character-blueprint-poc" content="v0.4.1"', 1)
    if "proxyBodyFrame='visibility-gated-v0.4.1'" not in text:
        raise SystemExit('character blueprint stable body-frame marker missing')
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
        published_text = make_proxy_stable(make_browser_safe(source_text))
        index.write_text(published_text, encoding='utf-8')
        index.chmod(0o644)
        deployed_text = index.read_text(encoding='utf-8')
        validate(deployed_text)
        required = ['type="importmap"', "from 'three/addons/controls/OrbitControls.js'", 'v0.4.1', "proxyBodyFrame='visibility-gated-v0.4.1'"]
        missing = [m for m in required if m not in deployed_text]
        if missing:
            raise SystemExit(f'character blueprint published artifact invalid: missing={missing}')
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
    if 'type="importmap"' not in final_text or "proxyBodyFrame='visibility-gated-v0.4.1'" not in final_text:
        raise SystemExit('character blueprint public artifact missing runtime safety markers')
    print(json.dumps({
        'ok': True,
        'release': 'character-blueprint-poc-v0.4.1',
        'target': str(TARGET),
        'public_path': '/poc/character-blueprint/',
        'marker': 'character-blueprint-poc/v0.4.1',
        'three_d_proxy': True,
        'interactive_part_linking': True,
        'browser_import_map': True,
        'visibility_gated_body_frame': True,
        'llm_tokens': 0,
        'sha256': digest(deployed),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
