#!/usr/bin/env python3
import argparse, json, math, os
from pathlib import Path

SCHEMA = 'character-ir-roundtrip/v0.1'


def load(path):
    return json.loads(Path(path).read_text())


def dump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')


def part_set(ir):
    parts = ir.get('inferred', {}).get('parts', []) or []
    out = []
    for p in parts:
        if isinstance(p, str): out.append(p)
        elif isinstance(p, dict): out.append(p.get('id') or p.get('part') or p.get('name'))
    return sorted({x for x in out if x})


def source_projection(ir):
    observed = ir.get('observed', {})
    inferred = ir.get('inferred', {})
    assumed = ir.get('assumed', {})
    props = inferred.get('proportions', {}) or {}
    return {
        'coverage': observed.get('pose', {}).get('coverage'),
        'parts': part_set(ir),
        'shoulder_width_norm': props.get('shoulder_width_norm'),
        'hip_width_norm': props.get('hip_width_norm'),
        'shoulder_hip_ratio': props.get('shoulder_hip_ratio'),
        'backside': assumed.get('backside') or assumed.get('unseen_backside'),
        'body_depth': assumed.get('body_depth'),
        'hair_depth': assumed.get('hair_depth'),
        'garment_depth': assumed.get('garment_depth'),
    }


def compile_scene(ir):
    src = source_projection(ir)
    parts = []
    coverage = src['coverage'] or 'unknown'
    for pid in src['parts']:
        role = 'semantic-part'
        if pid in ('hair', 'garment'): role = 'semantic-shell'
        parts.append({
            'id': pid,
            'role': role,
            'source': 'compiled_3d',
            'confidence': 1.0,
        })
    scene = {
        'schema': 'character-compiled-scene/v0.1',
        'compiler': ir.get('proxy_3d', {}).get('renderer') or 'character-ir-manifest-compiler/v0.1',
        'coverage': coverage,
        'parts': parts,
        'proportions': {
            'shoulder_width_norm': src['shoulder_width_norm'],
            'hip_width_norm': src['hip_width_norm'],
            'shoulder_hip_ratio': src['shoulder_hip_ratio'],
        },
        'completion_policy': {
            'backside': src['backside'],
            'body_depth': src['body_depth'],
            'hair_depth': src['hair_depth'],
            'garment_depth': src['garment_depth'],
        },
        'provenance': {
            'source_character_ir_schema': ir.get('schema'),
            'note': 'v0.1 scene manifest; not a mesh decompiler input',
        },
    }
    return scene


def extract_3d_ir(scene):
    props = scene.get('proportions', {})
    policy = scene.get('completion_policy', {})
    return {
        'schema': 'character-3d-derived-ir/v0.1',
        'source_kind': 'compiled-scene-manifest',
        'evidence_class': 'compiled_3d',
        'observed_3d': {
            'coverage': scene.get('coverage'),
            'parts': sorted(p.get('id') for p in scene.get('parts', []) if p.get('id')),
            'proportions': props,
        },
        'hypothesis': {
            'backside': {'value': policy.get('backside'), 'source': 'assumed_policy'},
            'body_depth': {'value': policy.get('body_depth'), 'source': 'assumed_policy'},
            'hair_depth': {'value': policy.get('hair_depth'), 'source': 'assumed_policy'},
            'garment_depth': {'value': policy.get('garment_depth'), 'source': 'assumed_policy'},
        },
        'provenance': scene.get('provenance', {}),
    }


def recovered_projection(ir3d):
    obs = ir3d.get('observed_3d', {})
    props = obs.get('proportions', {})
    hyp = ir3d.get('hypothesis', {})
    def hv(k):
        v = hyp.get(k)
        return v.get('value') if isinstance(v, dict) else v
    return {
        'coverage': obs.get('coverage'),
        'parts': sorted(obs.get('parts') or []),
        'shoulder_width_norm': props.get('shoulder_width_norm'),
        'hip_width_norm': props.get('hip_width_norm'),
        'shoulder_hip_ratio': props.get('shoulder_hip_ratio'),
        'backside': hv('backside'),
        'body_depth': hv('body_depth'),
        'hair_depth': hv('hair_depth'),
        'garment_depth': hv('garment_depth'),
    }


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try: return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-6)
        except Exception: pass
    return a == b


def diff(src, rec):
    preserved, changed, lost, invented = {}, {}, {}, {}
    for k in sorted(set(src) | set(rec)):
        a, b = src.get(k), rec.get(k)
        if a is None and b is not None: invented[k] = b
        elif a is not None and b is None: lost[k] = a
        elif same(a, b): preserved[k] = a
        else: changed[k] = {'source': a, 'recovered': b}
    total = len([k for k,v in src.items() if v is not None])
    kept = len(preserved)
    return {
        'preserved': preserved,
        'changed': changed,
        'lost': lost,
        'invented': invented,
        'summary': {
            'source_fields': total,
            'preserved_fields': kept,
            'preservation_ratio': round(kept / total, 4) if total else 1.0,
            'changed_fields': len(changed),
            'lost_fields': len(lost),
            'invented_fields': len(invented),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-ir', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()
    ir = load(args.input_ir)
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    src = source_projection(ir)
    scene = compile_scene(ir)
    ir3d = extract_3d_ir(scene)
    rec = recovered_projection(ir3d)
    report = {
        'schema': SCHEMA,
        'source_ir_schema': ir.get('schema'),
        'compiled_scene_schema': scene['schema'],
        'derived_ir_schema': ir3d['schema'],
        'mode': 'manifest-roundtrip',
        'limitations': ['v0.1 does not decompile triangle mesh; it validates the round-trip contract and information accounting'],
        'diff': diff(src, rec),
    }
    dump(out/'source-projection.json', src)
    dump(out/'compiled-scene.json', scene)
    dump(out/'ir-from-3d.json', ir3d)
    dump(out/'roundtrip-report.json', report)
    s = report['diff']['summary']
    print(json.dumps({'ok': True, 'schema': SCHEMA, **s}, ensure_ascii=False))
    if s['changed_fields'] or s['lost_fields']:
        raise SystemExit(2)

if __name__ == '__main__': main()
