#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYER = ROOT / 'scripts' / 'deploy_character_blueprint_poc.py'


@dataclass
class P:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0


def v(p: P) -> tuple[float, float, float]:
    return ((p.x - 0.5) * 4.0, (0.5 - p.y) * 5.0, -(p.z or 0.0) * 2.2)


def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, s): return tuple(x * s for x in a)
def mean(a, b): return mul(add(a, b), 0.5)
def norm(a): return math.sqrt(sum(x * x for x in a))
def normalize(a):
    n = norm(a)
    return tuple(x / n for x in a) if n else (0.0, 0.0, 0.0)


def reliable(p: P | None, threshold: float = 0.38) -> bool:
    return bool(p and p.visibility >= threshold and -0.12 <= p.x <= 1.12 and -0.12 <= p.y <= 1.12)


def coverage(lm: list[P]) -> str:
    def ok(i: int, threshold: float = 0.4) -> bool:
        p = lm[i]
        return p.visibility >= threshold and -0.08 <= p.x <= 1.08 and -0.08 <= p.y <= 1.08
    if ok(27) and ok(28): return 'full_body'
    if ok(25) and ok(26): return 'three_quarter'
    return 'upper_body'


def proxy_spec(lm: list[P]) -> dict:
    sh_l, sh_r = v(lm[11]), v(lm[12])
    shoulder = mean(sh_l, sh_r)
    sw = max(0.55, norm(sub(sh_l, sh_r)))
    cov = coverage(lm)
    if cov != 'upper_body' and reliable(lm[23], 0.42) and reliable(lm[24], 0.42):
        raw_hip = mean(v(lm[23]), v(lm[24]))
        d = sub(raw_hip, shoulder)
        ratio = norm(d) / sw
        if d[1] < -0.15 and 0.55 < ratio < 2.2:
            hip, torso_len = raw_hip, norm(d)
        else:
            torso_len, hip = sw * 1.18, add(shoulder, (0.0, -sw * 1.18, 0.0))
    else:
        torso_len, hip = sw * 1.18, add(shoulder, (0.0, -sw * 1.18, 0.0))
    torso_axis = normalize(sub(hip, shoulder))
    torso_center = mean(shoulder, hip)
    head_center = add(shoulder, (0.0, sw * 0.82, 0.0))
    if reliable(lm[7], 0.28) and reliable(lm[8], 0.28):
        ear_mid = mean(v(lm[7]), v(lm[8]))
        delta = sub(ear_mid, shoulder)
        if delta[1] > 0.1 and norm(delta) < sw * 1.6: head_center = ear_mid
    elif reliable(lm[0], 0.3):
        nose = v(lm[0]); delta = sub(nose, shoulder)
        if delta[1] > 0.1 and norm(delta) < sw * 1.6: head_center = add(nose, (0.0, sw * 0.12, 0.0))
    garment_r = max(0.21, sw * 0.285)
    parts = ['head', 'hair', 'body', 'garment']
    for label, a, b, c in [('left_arm',11,13,15),('right_arm',12,14,16)]:
        if reliable(lm[b], 0.22): parts.append(label)
    if cov != 'upper_body':
        for label, a, b, c in [('left_leg',23,25,27),('right_leg',24,26,28)]:
            if reliable(lm[a],0.35) and reliable(lm[b],0.3): parts.append(label)
    return {'coverage':cov,'shoulder_width':sw,'shoulder':shoulder,'hip':hip,'torso_axis':torso_axis,'torso_center':torso_center,'torso_len':torso_len,'head_center':head_center,'garment_r':garment_r,'parts':parts}


def base_landmarks() -> list[P]: return [P(0.5,0.5,visibility=0.0) for _ in range(33)]


def fixture_upper_body_portrait() -> list[P]:
    l=base_landmarks()
    vals={0:P(.59,.24,-.06,.99),7:P(.53,.27,0,.93),8:P(.65,.26,-.03,.91),11:P(.47,.43,.02,.96),12:P(.68,.42,-.03,.96),13:P(.42,.60,.02,.82),14:P(.73,.57,-.02,.80),15:P(.46,.77,.01,.62),16:P(.76,.73,-.01,.60),23:P(.51,.88,1.4,.08),24:P(.69,.90,-1.1,.07),25:P(.25,.35,2,.04),26:P(.95,.31,-2,.03),27:P(.08,.22,2.4,.02),28:P(.98,.20,-2.4,.02)}
    for i,p in vals.items(): l[i]=p
    return l


def fixture_full_body_standing() -> list[P]:
    l=base_landmarks()
    vals={0:P(.50,.12,0,.99),7:P(.46,.15,0,.95),8:P(.54,.15,0,.95),11:P(.42,.28,0,.99),12:P(.58,.28,0,.99),13:P(.36,.44,0,.95),14:P(.64,.44,0,.95),15:P(.34,.59,0,.92),16:P(.66,.59,0,.92),23:P(.45,.56,0,.98),24:P(.55,.56,0,.98),25:P(.45,.73,0,.96),26:P(.55,.73,0,.96),27:P(.45,.92,0,.94),28:P(.55,.92,0,.94)}
    for i,p in vals.items(): l[i]=p
    return l


def assert_upper_body(spec: dict) -> None:
    assert spec['coverage']=='upper_body', spec
    assert 'left_leg' not in spec['parts'] and 'right_leg' not in spec['parts'], spec
    verticality=abs(spec['torso_axis'][1])/max(1e-9,norm(spec['torso_axis']))
    assert verticality>=.97, (verticality,spec)
    assert spec['torso_axis'][1]<0, spec
    head_above=spec['head_center'][1]-spec['torso_center'][1]
    assert spec['shoulder_width']*.55 <= head_above <= spec['shoulder_width']*2.2, (head_above,spec)
    assert .9 <= spec['torso_len']/spec['shoulder_width'] <= 1.5, spec
    assert spec['garment_r']*2 < spec['torso_len']*.8, spec


def assert_full_body(spec: dict) -> None:
    assert spec['coverage']=='full_body', spec
    assert 'left_leg' in spec['parts'] and 'right_leg' in spec['parts'], spec
    assert spec['torso_axis'][1] < -.7, spec
    assert spec['head_center'][1] > spec['torso_center'][1], spec


def assert_deployer_contract() -> None:
    text=DEPLOYER.read_text(encoding='utf-8')
    required=["proxyBodyFrame='visibility-gated-v0.4.1'","cov!=='upper_body'","torsoLen=sw*1.18","character-blueprint-poc-v0.4.1"]
    missing=[m for m in required if m not in text]
    assert not missing, f'deployer/runtime contract drift: missing={missing}'


def main() -> int:
    assert_deployer_contract()
    upper=proxy_spec(fixture_upper_body_portrait()); full=proxy_spec(fixture_full_body_standing())
    assert_upper_body(upper); assert_full_body(full)
    result={'ok':True,'suite':'character-blueprint-geometry-regression/v1','cases':{'portrait_upperbody_regression_01':{'coverage':upper['coverage'],'parts':upper['parts'],'torso_verticality':round(abs(upper['torso_axis'][1]),4),'torso_to_shoulder':round(upper['torso_len']/upper['shoulder_width'],4)},'standing_fullbody_control_01':{'coverage':full['coverage'],'parts':full['parts']}}}
    print(json.dumps(result,ensure_ascii=False,sort_keys=True)); return 0


if __name__=='__main__': raise SystemExit(main())
