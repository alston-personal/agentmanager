#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path
from model2ir import extract_ir, stabilize_external_ir, compile_reversible_gltf, score_roundtrip

CORE={'pelvis','torso','head','left_arm','right_arm','left_leg','right_leg'}


def make_vrm1() -> dict:
    bones=['hips','spine','head','leftUpperArm','rightUpperArm','leftUpperLeg','rightUpperLeg']
    nodes=[{'name':f'opaque_{i}'} for i in range(len(bones))]
    return {
      'asset':{'version':'2.0'}, 'nodes':nodes,
      'extensionsUsed':['VRMC_vrm'],
      'extensions':{'VRMC_vrm':{'specVersion':'1.0','humanoid':{'humanBones':{b:{'node':i} for i,b in enumerate(bones)}}}}
    }


def make_vrm0() -> dict:
    bones=['hips','spine','head','leftUpperArm','rightUpperArm','leftUpperLeg','rightUpperLeg']
    nodes=[{'name':f'x{i}'} for i in range(len(bones))]
    return {
      'asset':{'version':'2.0'}, 'nodes':nodes,
      'extensionsUsed':['VRM'],
      'extensions':{'VRM':{'humanoid':{'humanBones':[{'bone':b,'node':i} for i,b in enumerate(bones)]}}}
    }


def write(path: Path, obj: dict): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--rigged',required=True)
    ap.add_argument('--simpleskin',required=True)
    ap.add_argument('--out',required=True)
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)

    vrm_results={}
    for label,obj in [('vrm1',make_vrm1()),('vrm0',make_vrm0())]:
        p=out/f'{label}.gltf'; write(p,obj)
        ir=extract_ir(p); ev=ir['vrm_humanoid_evidence']; cand=stabilize_external_ir(ir)
        assert ev is not None
        assert ev['body_plan']=='humanoid'
        assert ev['core_coverage']==1.0
        ids={x['id'] for x in cand['parts']}
        assert CORE <= ids, (label, sorted(CORE-ids))
        assert cand['body_plan']['source'].startswith('VRM-')
        assert cand['body_plan']['confidence'] >= .99
        carrier=compile_reversible_gltf(obj,cand)
        sp=out/f'{label}-stable.gltf'; write(sp,carrier)
        back=extract_ir(sp); score=score_roundtrip(cand,back)
        assert score['lossless_reversible']
        vrm_results[label]={'coverage':ev['core_coverage'],'confidence':cand['body_plan']['confidence'],'roundtrip':True}

    rig=json.loads(Path(args.rigged).read_text())
    for n in rig.get('nodes',[]): n.pop('name',None)
    for m in rig.get('meshes',[]): m.pop('name',None)
    rp=out/'rigged-no-names.gltf'; write(rp,rig)
    rir=extract_ir(rp); topo=rir['topology_evidence']; rc=stabilize_external_ir(rir)
    assert topo['kind']=='humanoid-topology', topo
    assert rc['body_plan']['kind']=='humanoid'
    assert rc['body_plan']['source']=='skeleton-topology'
    assert rc['body_plan']['side_assignment_status']=='unresolved'
    # topology may infer body-plan class, but must not invent left/right semantic parts
    ids={x['id'] for x in rc.get('parts',[])}
    assert not ({'left_arm','right_arm','left_leg','right_leg'} & ids), sorted(ids)
    carrier=compile_reversible_gltf(rig,rc)
    stable=out/'rigged-no-names-stable.gltf'; write(stable,carrier)
    rback=extract_ir(stable); rscore=score_roundtrip(rc,rback)
    assert rscore['lossless_reversible']

    simple=extract_ir(args.simpleskin)
    st= simple['topology_evidence']
    assert st['kind']=='unknown', st

    report={
      'schema':'model2ir-vrm-topology-regression/v0.6',
      'vrm':vrm_results,
      'unnamed_full_rig':{
        'topology_kind':topo['kind'], 'confidence':topo['confidence'],
        'side_assignments':topo['side_assignments'], 'roundtrip_exact':rscore['lossless_reversible']
      },
      'insufficient_simple_skin':{'topology_kind':st['kind'],'reason':st['reason'],'joint_count':st['joint_count']},
      'gate':{
        'vrm0_standard_semantics':True,
        'vrm1_standard_semantics':True,
        'unnamed_full_rig_body_plan':True,
        'unnamed_side_hallucination_avoided':True,
        'insufficient_rig_unknown':True,
        'post_stabilization_reversibility':1.0,
        'status':'PASS'
      }
    }
    write(out/'report.json',report)
    print(json.dumps(report['gate']))
if __name__=='__main__': main()
