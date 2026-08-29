#!/usr/bin/env python3
import argparse, json
from pathlib import Path


def load(p): return json.loads(Path(p).read_text())
def dump(p, x):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n')


def source_parts(ir):
    out=[]
    for p in ir.get('inferred',{}).get('parts',[]) or []:
        if isinstance(p,str): out.append(p)
        elif isinstance(p,dict): out.append(p.get('id') or p.get('part') or p.get('name'))
    return sorted({x for x in out if x})


def derived_candidates(ir3d):
    comps=ir3d.get('observed_3d',{}).get('components',[]) or []
    resolved=[]; unresolved=[]
    for c in comps:
        sem=c.get('semantic_candidate') or {}
        rec={
            'component': c.get('name'),
            'label': sem.get('label','unknown'),
            'confidence': sem.get('confidence',0),
            'source': sem.get('source'),
        }
        (unresolved if rec['label']=='unknown' else resolved).append(rec)
    return resolved, unresolved


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--image-ir',required=True)
    ap.add_argument('--three-d-ir',required=True)
    ap.add_argument('--output',required=True)
    args=ap.parse_args()
    image_ir=load(args.image_ir); ir3d=load(args.three_d_ir)
    src=source_parts(image_ir)
    resolved, unresolved=derived_candidates(ir3d)
    labels=sorted({x['label'] for x in resolved})
    srcset=set(src); labset=set(labels)
    matched=sorted(srcset & labset)
    source_not_recovered=sorted(srcset-labset)
    candidate_only=sorted(labset-srcset)
    geometry=ir3d.get('observed_3d',{}).get('geometry',{}) or {}
    assumed=image_ir.get('assumed',{}) or {}

    suggestions=[]
    for x in source_not_recovered:
        suggestions.append({
            'kind':'missing-3d-semantic-evidence',
            'field':f'part:{x}',
            'action':'improve 3D semantic extraction or compiler traceability; do not assume the part is absent',
        })
    for x in candidate_only:
        suggestions.append({
            'kind':'candidate-new-3d-information',
            'field':f'part:{x}',
            'action':'keep as hypothesis until image evidence, another view, or user confirmation supports it',
        })
    if unresolved:
        suggestions.append({
            'kind':'unresolved-3d-components',
            'count':len(unresolved),
            'action':'segment/classify geometry before attempting canonical IR promotion',
        })

    report={
        'schema':'character-ir-reconciliation/v0.1',
        'inputs':{
            'image_ir_schema':image_ir.get('schema'),
            'three_d_ir_schema':ir3d.get('schema'),
            'three_d_source_kind':ir3d.get('source_kind'),
        },
        'semantic_comparison':{
            'image_ir_parts':src,
            'resolved_3d_labels':labels,
            'matched':matched,
            'image_parts_not_recovered_from_3d':source_not_recovered,
            '3d_candidates_not_in_image_ir':candidate_only,
            'unresolved_3d_components':unresolved,
        },
        'geometry_evidence_from_3d':geometry,
        'image_ir_completion_assumptions':assumed,
        'canonical_update_policy':{
            'automatic_promotions':[],
            'rule':'3D generator output is candidate evidence, never canonical truth by itself',
        },
        'refinement_suggestions':suggestions,
        'summary':{
            'image_part_count':len(src),
            'resolved_3d_label_count':len(labels),
            'matched_part_count':len(matched),
            'unresolved_3d_component_count':len(unresolved),
            'semantic_recovery_ratio':round(len(matched)/len(src),4) if src else 1.0,
        },
    }
    dump(args.output,report)
    print(json.dumps({'ok':True, **report['summary']},ensure_ascii=False))

if __name__=='__main__': main()
