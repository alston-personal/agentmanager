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
SOURCE_MARKERS = [
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

ENVELOPE_FUNCTIONS = r'''let lastSilhouetteProfile=null;
function coverage(l){const ok=(i,t=.4)=>{const p=l[i];return !!p&&(p.visibility??0)>=t&&p.x>=-.08&&p.x<=1.08&&p.y>=-.08&&p.y<=1.08};return ok(27)&&ok(28)?'full_body':ok(25)&&ok(26)?'three_quarter':'upper_body'}
function reliablePoint(l,i,t=.38){const p=l[i];return !!p&&(p.visibility??0)>=t&&p.x>=-.12&&p.x<=1.12&&p.y>=-.12&&p.y<=1.12}
function clamp01(x){return Math.max(0,Math.min(1,x))}
function rgbDistance(d,i,bg){const dr=d[i]-bg[0],dg=d[i+1]-bg[1],db=d[i+2]-bg[2];return Math.sqrt(dr*dr+dg*dg+db*db)}
function estimateBorderBackground(data,w,h){let r=0,g=0,b=0,n=0;const step=Math.max(1,Math.floor(Math.min(w,h)/40));const take=(x,y)=>{const i=(y*w+x)*4;r+=data[i];g+=data[i+1];b+=data[i+2];n++};for(let x=0;x<w;x+=step){take(x,0);take(x,h-1)}for(let y=step;y<h-step;y+=step){take(0,y);take(w-1,y)}return n?[r/n,g/n,b/n]:[255,255,255]}
function rowForegroundRun(data,w,h,yn,cxn,halfNorm,bg,threshold=46){const y=Math.max(0,Math.min(h-1,Math.round(clamp01(yn)*(h-1)))),cx=Math.round(clamp01(cxn)*(w-1)),x0=Math.max(0,Math.floor((cxn-halfNorm)*w)),x1=Math.min(w-1,Math.ceil((cxn+halfNorm)*w));let runs=[],start=-1;for(let x=x0;x<=x1;x++){const fg=rgbDistance(data,(y*w+x)*4,bg)>threshold;if(fg&&start<0)start=x;if((!fg||x===x1)&&start>=0){const end=fg&&x===x1?x:x-1;if(end-start>=2)runs.push([start,end]);start=-1}}if(!runs.length)return null;runs.sort((a,b)=>{const ac=(a[0]+a[1])/2,bc=(b[0]+b[1])/2,ad=cx>=a[0]&&cx<=a[1]?0:Math.abs(ac-cx),bd=cx>=b[0]&&cx<=b[1]?0:Math.abs(bc-cx);return ad-bd||(b[1]-b[0])-(a[1]-a[0])});const q=runs[0],left=q[0]/w,right=q[1]/w;return{left_norm:left,right_norm:right,width_norm:Math.max(1/w,right-left),center_norm:(left+right)/2}}
function fallbackRows(widthNorm,centerNorm,count=7){return Array.from({length:count},(_,i)=>{const t=i/(count-1),shape=.88+.18*Math.sin(Math.PI*t);return{t,width_norm:widthNorm*shape,center_norm:centerNorm,source:'pose-fallback'}})}
function extractSilhouetteProfile(l){if(!img?.naturalWidth||!img?.naturalHeight)return null;const maxDim=320,scale=Math.min(1,maxDim/Math.max(img.naturalWidth,img.naturalHeight)),c=document.createElement('canvas');c.width=Math.max(32,Math.round(img.naturalWidth*scale));c.height=Math.max(32,Math.round(img.naturalHeight*scale));const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(img,0,0,c.width,c.height);const im=ctx.getImageData(0,0,c.width,c.height),data=im.data,bg=estimateBorderBackground(data,c.width,c.height),cov=coverage(l);const shoulderNorm=Math.max(.035,Math.abs(l[12].x-l[11].x)),shoulderY=(l[11].y+l[12].y)/2,shoulderX=(l[11].x+l[12].x)/2;let hipY=shoulderY+shoulderNorm*1.18,hipX=shoulderX;if(cov!=='upper_body'&&reliablePoint(l,23,.35)&&reliablePoint(l,24,.35)){hipY=(l[23].y+l[24].y)/2;hipX=(l[23].x+l[24].x)/2;if(hipY<=shoulderY+.08||hipY>shoulderY+shoulderNorm*2.1){hipY=shoulderY+shoulderNorm*1.18;hipX=shoulderX}}else hipY=Math.min(.98,shoulderY+Math.max(.20,shoulderNorm*1.35));const torso=[];for(let i=0;i<8;i++){const t=i/7,yn=shoulderY+(hipY-shoulderY)*t,cxn=shoulderX+(hipX-shoulderX)*t,run=rowForegroundRun(data,c.width,c.height,yn,cxn,shoulderNorm*.95,bg,46);if(run)torso.push({t,...run,source:'image-silhouette'})}const torsoRows=torso.length>=5?torso:fallbackRows(shoulderNorm*1.12,shoulderX,8);const earX=reliablePoint(l,7,.2)&&reliablePoint(l,8,.2)?(l[7].x+l[8].x)/2:(l[0]?.x??shoulderX),faceY=l[0]?.y??Math.max(.05,shoulderY-shoulderNorm*.9),hairTop=Math.max(0,faceY-shoulderNorm*.78),hairBottom=Math.min(shoulderY+shoulderNorm*.08,faceY+shoulderNorm*1.05),hair=[];for(let i=0;i<8;i++){const t=i/7,yn=hairTop+(hairBottom-hairTop)*t,run=rowForegroundRun(data,c.width,c.height,yn,earX,shoulderNorm*.82,bg,42);if(run)hair.push({t,...run,source:'image-silhouette'})}const hairRows=hair.length>=4?hair:fallbackRows(shoulderNorm*.92,earX,8);return{engine:'border-evidence-silhouette/v0.5',canvas:{width:c.width,height:c.height},background_rgb:bg.map(x=>Math.round(x)),shoulder_width_norm:+shoulderNorm.toFixed(4),torso:{rows:torsoRows,confidence:+Math.min(1,torso.length/8).toFixed(3)},hair:{rows:hairRows,confidence:+Math.min(1,hair.length/8).toFixed(3)}}}
function envelopeGeometry(rows,length,sw,shoulderNorm,depthRatio,refCenterNorm,widthScale=1,segments=20){const verts=[],idx=[],safeShoulder=Math.max(.035,shoulderNorm);for(let i=0;i<rows.length;i++){const p=rows[i],ratio=Math.max(.52,Math.min(1.75,p.width_norm/safeShoulder)),rx=Math.max(.10,sw*ratio*.5*widthScale),rz=Math.max(.08,rx*depthRatio),y=length*(.5-p.t),xo=(p.center_norm-refCenterNorm)*4*.72;for(let j=0;j<segments;j++){const a=2*Math.PI*j/segments;verts.push(xo+rx*Math.cos(a),y,rz*Math.sin(a))}}for(let i=0;i<rows.length-1;i++)for(let j=0;j<segments;j++){const n=(j+1)%segments,a=i*segments+j,b=i*segments+n,c=(i+1)*segments+j,d=(i+1)*segments+n;idx.push(a,c,b,b,c,d)}const top=verts.length/3,bottom=top+1;verts.push(0,length*.5,0,0,-length*.5,0);for(let j=0;j<segments;j++){const n=(j+1)%segments;idx.push(top,n,j);const a=(rows.length-1)*segments+j,b=(rows.length-1)*segments+n;idx.push(bottom,a,b)}const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(verts,3));geo.setIndex(idx);geo.computeVertexNormals();return geo}
function rebuild3D(l){init3D();if(root)scene.remove(root);root=new THREE.Group();scene.add(root);meshParts=[];const shL=v(l,11),shR=v(l,12),shoulder=mean(shL,shR),sw=Math.max(.55,shL.distanceTo(shR)),cov=coverage(l),shoulderNorm=Math.max(.035,Math.abs(l[12].x-l[11].x)),shoulderCenterNorm=(l[11].x+l[12].x)/2;let hip,torsoLen,hipCenterNorm=shoulderCenterNorm;if(cov!=='upper_body'&&reliablePoint(l,23,.42)&&reliablePoint(l,24,.42)){const rawHip=mean(v(l,23),v(l,24)),d=rawHip.clone().sub(shoulder),ratio=d.length()/sw;if(d.y<-.15&&ratio>.55&&ratio<2.2){hip=rawHip;torsoLen=d.length();hipCenterNorm=(l[23].x+l[24].x)/2}else{torsoLen=sw*1.18;hip=shoulder.clone().add(new THREE.Vector3(0,-torsoLen,0))}}else{torsoLen=sw*1.18;hip=shoulder.clone().add(new THREE.Vector3(0,-torsoLen,0))}const torsoAxis=hip.clone().sub(shoulder).normalize(),torsoCenter=mean(shoulder,hip),profile=lastSilhouetteProfile||{torso:{rows:fallbackRows(shoulderNorm*1.1,shoulderCenterNorm,8)},hair:{rows:fallbackRows(shoulderNorm*.9,l[0]?.x??shoulderCenterNorm,8)},engine:'pose-fallback'};let headCenter=shoulder.clone().add(new THREE.Vector3(0,sw*.82,0));if(reliablePoint(l,7,.28)&&reliablePoint(l,8,.28)){const earMid=mean(v(l,7),v(l,8)),delta=earMid.clone().sub(shoulder);if(delta.y>.1&&delta.length()<sw*1.6)headCenter=earMid}else if(reliablePoint(l,0,.3)){const nose=v(l,0),delta=nose.clone().sub(shoulder);if(delta.y>.1&&delta.length()<sw*1.6)headCenter=nose.clone().add(new THREE.Vector3(0,sw*.12,0))}const headR=Math.max(.24,sw*.31);addMesh(new THREE.SphereGeometry(1,28,20),'head',headCenter,new THREE.Vector3(headR*.80,headR,headR*.70));const hairRows=profile.hair?.rows||fallbackRows(shoulderNorm*.9,l[0]?.x??shoulderCenterNorm,8),hairLen=Math.max(sw*1.05,headR*2.25),hairRef=l[0]?.x??shoulderCenterNorm,hair=addMesh(envelopeGeometry(hairRows,hairLen,sw,shoulderNorm,.72,hairRef,1.02,22),'hair',headCenter.clone().add(new THREE.Vector3(0,headR*.12,-headR*.02)));hair.scale.z=1.02;const torsoRows=profile.torso?.rows||fallbackRows(shoulderNorm*1.1,shoulderCenterNorm,8),body=addMesh(envelopeGeometry(torsoRows,torsoLen,sw,shoulderNorm,.48,(shoulderCenterNorm+hipCenterNorm)/2,.82,22),'body',torsoCenter);body.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),torsoAxis);const garment=addMesh(envelopeGeometry(torsoRows,torsoLen*1.03,sw,shoulderNorm,.58,(shoulderCenterNorm+hipCenterNorm)/2,1.02,22),'garment',torsoCenter.clone().add(new THREE.Vector3(0,-sw*.02,0)));garment.quaternion.copy(body.quaternion);const armChains=[['left_arm',11,13,15],['right_arm',12,14,16]];for(const [part,a,b,c] of armChains){if(!reliablePoint(l,b,.22))continue;const A=v(l,a),B=v(l,b);cylinderBetween(A,B,Math.max(.055,sw*.09),part);if(reliablePoint(l,c,.2))cylinderBetween(B,v(l,c),Math.max(.05,sw*.08),part)}if(cov!=='upper_body'){const legChains=[['left_leg',23,25,27],['right_leg',24,26,28]];for(const [part,a,b,c] of legChains){if(!reliablePoint(l,a,.35)||!reliablePoint(l,b,.3))continue;const A=v(l,a),B=v(l,b);cylinderBetween(A,B,Math.max(.07,sw*.115),part);if(reliablePoint(l,c,.28))cylinderBetween(B,v(l,c),Math.max(.06,sw*.095),part)}}root.userData.proxyBodyFrame='silhouette-envelope-v0.5';root.userData.silhouetteEngine=profile.engine||'pose-fallback';viewerEmpty.style.display='none';fitCamera();selectPart(selected)}'''

BUILD_IR = r'''function buildIR(l){const shoulder=Math.hypot(l[11].x-l[12].x,l[11].y-l[12].y),hip=Math.hypot(l[23].x-l[24].x,l[23].y-l[24].y),vis=l.reduce((s,p)=>s+(p.visibility??1),0)/l.length,cov=coverage(l),sil=lastSilhouetteProfile;return{schema:SCHEMA,version:VERSION,llm_tokens:0,observed:{image:{width:img.naturalWidth,height:img.naturalHeight},pose:{landmarks:33,mean_visibility:+vis.toFixed(3),coverage:cov},silhouette:sil?{engine:sil.engine,background_rgb:sil.background_rgb,torso_rows:sil.torso.rows.length,torso_confidence:sil.torso.confidence,hair_rows:sil.hair.rows.length,hair_confidence:sil.hair.confidence}:null},inferred:{proportions:{shoulder_width_norm:+shoulder.toFixed(4),hip_width_norm:+hip.toFixed(4),shoulder_hip_ratio:+(shoulder/Math.max(.001,hip)).toFixed(3)},parts:['head','hair','body','garment','left_arm','right_arm'].concat(cov==='upper_body'?[]:['left_leg','right_leg']),envelope:{torso_profile:sil?.torso?.rows||[],hair_profile:sil?.hair?.rows||[]}},assumed:{backside:'unobserved',body_depth:'elliptical depth from silhouette width',hair_depth:'silhouette envelope with assumed rear depth',garment_depth:'silhouette envelope with outer-shell depth'},proxy_3d:{renderer:'threejs-silhouette-envelope/v0.5',interactive:true,source:'pose+image-silhouette+deterministic-geometry'}}}'''


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_source(text: str) -> None:
    missing = [m for m in SOURCE_MARKERS if m not in text]
    if missing:
        raise SystemExit(f'character blueprint source invalid: missing={missing}')
    if all(x in text for x in FORBIDDEN_FALLBACK):
        raise SystemExit('character blueprint source unexpectedly contains Studio fallback identity')


def make_browser_safe(text: str) -> str:
    old = f'<script type="module">\n{THREE_DIRECT}\n{ORBIT_DIRECT}'
    new = f'{IMPORT_MAP}\n<script type="module">\n{THREE_MAPPED}\n{ORBIT_MAPPED}'
    if old not in text:
        raise SystemExit('character blueprint deploy transform failed: expected Three.js direct imports not found')
    return text.replace(old, new, 1)


def make_envelope_v05(text: str) -> str:
    pattern = re.compile(r"function coverage\(l\)\{.*?\}\nfunction buildIR\(l\)\{.*?\}\nlet renderer", re.S)
    if not pattern.search(text):
        raise SystemExit('character blueprint v0.5 transform failed: coverage/buildIR boundary missing')
    replacement = ENVELOPE_FUNCTIONS.split('function rebuild3D', 1)[0] + BUILD_IR + '\nlet renderer'
    text = pattern.sub(replacement, text, count=1)
    rebuild_pattern = re.compile(r"function rebuild3D\(l\)\{.*?viewerEmpty\.style\.display='none';fitCamera\(\);selectPart\(selected\)\}", re.S)
    rebuild = 'function rebuild3D' + ENVELOPE_FUNCTIONS.split('function rebuild3D', 1)[1]
    text, count = rebuild_pattern.subn(rebuild, text, count=1)
    if count != 1:
        raise SystemExit(f'character blueprint v0.5 transform failed: rebuild matches={count}')
    old_analyze = "currentLm=res.landmarks[0];currentIR=buildIR(currentLm);selected='body';draw2D();rebuild3D(currentLm);"
    new_analyze = "currentLm=res.landmarks[0];lastSilhouetteProfile=extractSilhouetteProfile(currentLm);currentIR=buildIR(currentLm);selected='body';draw2D();rebuild3D(currentLm);"
    if old_analyze not in text:
        raise SystemExit('character blueprint v0.5 transform failed: analyze pipeline marker missing')
    text = text.replace(old_analyze, new_analyze, 1)
    text = text.replace('data-version="0.4.0"', 'data-version="0.5.0"', 1)
    text = text.replace('meta name="character-blueprint-poc" content="v0.4.0"', 'meta name="character-blueprint-poc" content="v0.5.0"', 1)
    text = text.replace('<title>Character Blueprint POC v0.4</title>', '<title>Character Blueprint POC v0.5</title>', 1)
    text = text.replace('POC v0.4 · browser-local', 'POC v0.5 · silhouette envelope', 1)
    text = text.replace('CHARACTER BLUEPRINT · IMAGE → 3D PROXY', 'CHARACTER BLUEPRINT · IMAGE → 3D ENVELOPE', 1)
    text = text.replace("const VERSION='0.4.0', SCHEMA='character-blueprint-ir/v0.4';", "const VERSION='0.5.0', SCHEMA='character-blueprint-ir/v0.5';", 1)
    text = text.replace("a.download='character-blueprint-ir-v0.4.json'", "a.download='character-blueprint-ir-v0.5.json'", 1)
    text = text.replace('頭、四肢與軀幹來自 Pose / 比例；頭髮與衣服目前是依頭部與軀幹建立的<strong>深度假設</strong>', '軀幹、衣服與頭髮的正面寬度已開始來自<strong>圖片 silhouette</strong>；背面深度仍是明確標示的假設', 1)
    if "proxyBodyFrame='silhouette-envelope-v0.5'" not in text or 'border-evidence-silhouette/v0.5' not in text:
        raise SystemExit('character blueprint v0.5 envelope markers missing')
    return text


def make_browser_testable(text: str) -> str:
    old = "window.CharacterBlueprintPOC={version:VERSION,schema:SCHEMA,threeDProxy:true,interactivePartLinking:true,llmTokens:0};"
    new = """window.CharacterBlueprintPOC={version:VERSION,schema:SCHEMA,threeDProxy:true,interactivePartLinking:true,silhouetteEnvelope:true,llmTokens:0,browserSelfTest:true,selfTestLandmarks:(l)=>{currentLm=l;lastSilhouetteProfile=null;currentIR=buildIR(l);selected='body';rebuild3D(l);const parts=[...new Set(meshParts.map(x=>x.userData.part))];selectPart('head');return{coverage:coverage(l),parts,selected,meshCount:meshParts.length,canvasCount:viewer.querySelectorAll('canvas').length,bodyFrame:root?.userData?.proxyBodyFrame||null,silhouetteEngine:root?.userData?.silhouetteEngine||null}}};"""
    if old not in text:
        raise SystemExit('character blueprint browser self-test transform failed: public API marker missing')
    return text.replace(old, new, 1)


def validate_published(text: str) -> None:
    required = [
        'data-version="0.5.0"',
        'character-blueprint-ir/v0.5',
        'threejs-silhouette-envelope/v0.5',
        'border-evidence-silhouette/v0.5',
        "proxyBodyFrame='silhouette-envelope-v0.5'",
        'silhouetteEnvelope:true',
        'browserSelfTest:true',
        'type="importmap"',
        "from 'three/addons/controls/OrbitControls.js'",
        '"llm_tokens":0',
    ]
    missing = [m for m in required if m not in text]
    if missing:
        raise SystemExit(f'character blueprint published artifact invalid: missing={missing}')


def main() -> int:
    if not SOURCE.is_file():
        raise SystemExit(f'missing source: {SOURCE}')
    source_text = SOURCE.read_text(encoding='utf-8')
    validate_source(source_text)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.parent.chmod(0o755)
    tmp: Path | None = Path(tempfile.mkdtemp(prefix='.character-blueprint-', dir=str(TARGET.parent)))
    tmp.chmod(0o755)
    try:
        index = tmp / 'index.html'
        published_text = make_browser_testable(make_envelope_v05(make_browser_safe(source_text)))
        validate_published(published_text)
        index.write_text(published_text, encoding='utf-8')
        index.chmod(0o644)
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
    validate_published(final_text)
    print(json.dumps({
        'ok': True,
        'release': 'character-blueprint-poc-v0.5.0',
        'target': str(TARGET),
        'public_path': '/poc/character-blueprint/',
        'marker': 'character-blueprint-poc/v0.5.0',
        'three_d_envelope': True,
        'silhouette_engine': 'border-evidence-silhouette/v0.5',
        'interactive_part_linking': True,
        'browser_import_map': True,
        'browser_self_test': True,
        'llm_tokens': 0,
        'sha256': digest(deployed),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
