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


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, s):
    return tuple(x * s for x in a)


def mean(a, b):
    return mul(add(a, b), 0.5)


def norm(a):
    return math.sqrt(sum(x * x for x in a))


def normalize(a):
    n = norm(a)
    return tuple(x / n for x in a) if n else (0.0, 0.0, 0.0)


def reliable(p: P | None, threshold: float = 0.38) -> bool:
    return bool(
        p
        and p.visibility >= threshold
        and -0.12 <= p.x <= 1.12
        and -0.12 <= p.y <= 1.12
    )


def coverage(lm: list[P]) -> str:
    def ok(i: int, threshold: float = 0.4) -> bool:
        p = lm[i]
        return p.visibility >= threshold and -0.08 <= p.x <= 1.08 and -0.08 <= p.y <= 1.08

    if ok(27) and ok(28):
        return 'full_body'
    if ok(25) and ok(26):
        return 'three_quarter'
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
            hip = raw_hip
            torso_len = norm(d)
        else:
            torso_len = sw * 1.18
            hip = add(shoulder, (0.0, -torso_len, 0.0))
    else:
        torso_len = sw * 1.18
        hip = add(shoulder, (0.0, -torso_len, 0.0))

    torso_axis = normalize(sub(hip, shoulder))
    torso_center = mean(shoulder, hip)
    head_center = add(shoulder, (0.0, sw * 0.82, 0.0))

    if reliable(lm[7], 0.28) and reliable(lm[8], 0.28):
        ear_mid = mean(v(lm[7]), v(lm[8]))
        delta = sub(ear_mid, shoulder)
        if delta[1] > 0.1 and norm(delta) < sw * 1.6:
            head_center = ear_mid
    elif reliable(lm[0], 0.3):
        nose = v(lm[0])
        delta = sub(nose, shoulder)
        if delta[1] > 0.1 and norm(delta) < sw * 1.6:
            head_center = add(nose, (0.0, sw * 0.12, 0.0))

    head_r = max(0.24, sw * 0.31)
    body_r = max(0.18, sw * 0.24)
    garment_r = max(0.21, sw * 0.285)
    parts = ['head', 'hair', 'body', 'garment']

    for label, a, b, c in [('left_arm', 11, 13, 15), ('right_arm', 12, 14, 16)]:
        if reliable(lm[b], 0.22):
            parts.append(label)

    if cov != 'upper_body':
        for label, a, b, c in [('left_leg', 23, 25, 27), ('right_leg', 24, 26, 28)]:
            if reliable(lm[a], 0.35) and reliable(lm[b], 0.3):
                parts.append(label)

    return {
        'coverage': cov,
        'shoulder_width': sw,
        'shoulder': shoulder,
        'hip': hip,
        'torso_axis': torso_axis,
        'torso_center': torso_center,
        'torso_len': torso_len,
        'head_center': head_center,
        'head_r': head_r,
        'body_r': body_r,
        'garment_r': garment_r,
        'parts': parts,
    }


def base_landmarks() -> list[P]:
    return [P(0.5, 0.5, visibility=0.0) for _ in range(33)]


def fixture_upper_body_portrait() -> list[P]:
    # Representative of the user's half-body portrait regression case:
    # shoulders and arms visible, hips/knees/ankles intentionally unreliable.
    l = base_landmarks()
    l[0] = P(0.59, 0.24, -0.06, 0.99)
    l[7] = P(0.53, 0.27, 0.00, 0.93)
    l[8] = P(0.65, 0.26, -0.03, 0.91)
    l[11] = P(0.47, 0.43, 0.02, 0.96)
    l[12] = P(0.68, 0.42, -0.03, 0.96)
    l[13] = P(0.42, 0.60, 0.02, 0.82)
    l[14] = P(0.73, 0.57, -0.02, 0.80)
    l[15] = P(0.46, 0.77, 0.01, 0.62)
    l[16] = P(0.76, 0.73, -0.01, 0.60)
    # Hidden lower body: plausible-looking coordinates but very low confidence.
    l[23] = P(0.51, 0.88, 1.4, 0.08)
    l[24] = P(0.69, 0.90, -1.1, 0.07)
    l[25] = P(0.25, 0.35, 2.0, 0.04)
    l[26] = P(0.95, 0.31, -2.0, 0.03)
    l[27] = P(0.08, 0.22, 2.4, 0.02)
    l[28] = P(0.98, 0.20, -2.4, 0.02)
    return l


def fixture_full_body_standing() -> list[P]:
    l = base_landmarks()
    l[0] = P(0.50, 0.12, 0.0, 0.99)
    l[7] = P(0.46, 0.15, 0.0, 0.95)
    l[8] = P(0.54, 0.15, 0.0, 0.95)
    l[11] = P(0.42, 0.28, 0.0, 0.99)
    l[12] = P(0.58, 0.28, 0.0, 0.99)
    l[13] = P(0.36, 0.44, 0.0, 0.95)
    l[14] = P(0.64, 0.44, 0.0, 0.95)
    l[15] = P(0.34, 0.59, 0.0, 0.92)
    l[16] = P(0.66, 0.59, 0.0, 0.92)
    l[23] = P(0.45, 0.56, 0.0, 0.98)
    l[24] = P(0.55, 0.56, 0.0, 0.98)
    l[25] = P(0.45, 0.73, 0.0, 0.96)
    l[26] = P(0.55, 0.73, 0.0, 0.96)
    l[27] = P(0.45, 0.92, 0.0, 0.94)
    l[28] = P(0.55, 0.92, 0.0, 0.94)
    return l


def assert_upper_body(spec: dict) -> None:
    assert spec['coverage'] == 'upper_body', spec
    assert 'left_leg' not in spec['parts'] and 'right_leg' not in spec['parts'], spec
    # A stable upper-body torso must be essentially vertical in the normalized 3D frame.
    verticality = abs(spec['torso_axis'][1]) / max(1e-9, norm(spec['torso_axis']))
    assert verticality >= 0.97, (verticality, spec)
    assert spec['torso_axis'][1] < 0, spec
    # Head must be clearly above the shoulder/torso center, but not detached absurdly far away.
    head_above_torso = spec['head_center'][1] - spec['torso_center'][1]
    assert spec['shoulder_width'] * 0.55 <= head_above_torso <= spec['shoulder_width'] * 2.2, (head_above_torso, spec)
    # The torso cannot become the giant horizontal capsule seen in v0.4.
    assert 0.9 <= spec['torso_len'] / spec['shoulder_width'] <= 1.5, spec
    assert spec['garment_r'] * 2 < spec['torso_len'] * 0.8, spec


def assert_full_body(spec: dict) -> None:
    assert spec['coverage'] == 'full_body', spec
    assert 'left_leg' in spec['parts'] and 'right_leg' in spec['parts'], spec
    assert spec['torso_axis'][1] < -0.7, spec
    assert spec['head_center'][1] > spec['torso_center'][1], spec


def assert_deployer_contract() -> None:
    text = DEPLOYER.read_text(encoding='utf-8')
    required = [
        "proxyBodyFrame='visibility-gated-v0.4.1'",
        "cov!=='upper_body'",
        "torsoLen=sw*1.18",
        "character-blueprint-poc-v0.4.1",
    ]
    missing = [m for m in required if m not in text]
    assert not missing, f'deployer/runtime contract drift: missing={missing}'


def main() -> int:
    assert_deployer_contract()
    upper = proxy_spec(fixture_upper_body_portrait())
    full = proxy_spec(fixture_full_body_standing())
    assert_upper_body(upper)
    assert_full_body(full)
    result = {
        'ok': True,
        'suite': 'character-blueprint-geometry-regression/v1',
        'cases': {
            'portrait_upperbody_regression_01': {
                'coverage': upper['coverage'],
                'parts': upper['parts'],
                'torso_verticality': round(abs(upper['torso_axis'][1]), 4),
                'torso_to_shoulder': round(upper['torso_len'] / upper['shoulder_width'], 4),
            },
            'standing_fullbody_control_01': {
                'coverage': full['coverage'],
                'parts': full['parts'],
            },
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
