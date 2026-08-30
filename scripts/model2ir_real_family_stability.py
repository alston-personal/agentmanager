#!/usr/bin/env python3
from __future__ import annotations

import argparse, copy, json
from pathlib import Path
from model2ir import extract_ir, stabilize_external_ir, compile_reversible_gltf, score_roundtrip, ir_digest

CORE={'torso','left_arm','right_arm','left_leg','right_leg','neck'}

def labels(ir):
    return set((ir.get('semantic_evidence_v03') or {}).get('parts',{}))

def stabilize(path: Path, out: Path):
    m=extract_ir(path)
    c=stabilize_external_ir(m)
    raw=json.loads(path.read_text())
    carrier=compile_reversible_gltf(raw,c)
    p=out/f'{path.stem}-stable.gltf'
    p.write_text(json.dumps(carrier,ensure_ascii=False,indent=2)+'\n')
    back=extract_ir(p)
    s=score_roundtrip(c,back)
    assert s['lossless_reversible'] is True
    return m,c,s

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cesium',required=True)
    ap.add_argument('--rigged',required=True)
    ap.add_argument('--negative',required=True)
    ap.add_argument('--out',required=True)
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    results={}
    human_labels=[]
    for name,path in [('cesium',Path(args.cesium)),('rigged',Path(args.rigged))]:
        first=extract_ir(path); second=extract_ir(path)
        c1=stabilize_external_ir(first); c2=stabilize_external_ir(second)
        assert ir_digest(c1)==ir_digest(c2)
        assert (first.get('semantic_evidence_v03') or {}).get('body_plan',{}).get('kind')=='humanoid'
        labs=labels(first); human_labels.append(labs)
        assert len(CORE-labs)<=1, (name,sorted(CORE-labs))
        m,c,s=stabilize(path,out)
        results[name]={
          'labels':sorted(labs),
          'candidate_digest':ir_digest(c),
          'joint_count':c['skeleton'].get('joint_count',0),
          'roundtrip_exact':s['lossless_reversible'],
        }

    shared=set.intersection(*human_labels)
    assert len(CORE-shared)<=1, sorted(CORE-shared)

    neg=extract_ir(args.negative)
    assert (neg.get('semantic_evidence_v03') or {}).get('body_plan',{}).get('kind')!='humanoid'

    # Remove all node names from a real rig. The extractor must lose semantics rather than hallucinate them.
    sanitized=json.loads(Path(args.rigged).read_text())
    for n in sanitized.get('nodes',[]): n.pop('name',None)
    for m in sanitized.get('meshes',[]): m.pop('name',None)
    sanp=out/'rigged-no-names.gltf'; sanp.write_text(json.dumps(sanitized,indent=2)+'\n')
    sani=extract_ir(sanp)
    assert (sani.get('semantic_evidence_v03') or {}).get('body_plan',{}).get('kind')!='humanoid'
    sc=stabilize_external_ir(sani)
    carrier=compile_reversible_gltf(sanitized,sc)
    stable=out/'rigged-no-names-stable.gltf'; stable.write_text(json.dumps(carrier,indent=2)+'\n')
    back=extract_ir(stable)
    score=score_roundtrip(sc,back)
    assert score['lossless_reversible'] is True

    report={
      'schema':'model2ir-real-family-stability/v0.5',
      'humanoid_models':results,
      'shared_core_labels':sorted(shared),
      'negative_control_kind':(neg.get('semantic_evidence_v03') or {}).get('body_plan',{}).get('kind'),
      'name_erasure':{
        'body_plan_after_erasure':(sani.get('semantic_evidence_v03') or {}).get('body_plan',{}).get('kind'),
        'hallucination_avoided':True,
        'stabilized_roundtrip_exact':score['lossless_reversible'],
      },
      'gate':{
        'two_independent_humanoids_consistent':True,
        'candidate_repeatability':1.0,
        'post_stabilization_reversibility':1.0,
        'negative_control_correct':True,
        'unknown_when_evidence_removed':True,
        'status':'PASS'
      }
    }
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['gate']))
if __name__=='__main__': main()
