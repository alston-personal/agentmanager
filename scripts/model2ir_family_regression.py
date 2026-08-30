#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path
from model2ir import extract_ir, diff_ir


def make_gltf(path: Path, names: list[str]):
    accessors=[]; meshes=[]; nodes=[]
    for i,name in enumerate(names):
        pos=len(accessors); idx=pos+1
        accessors.extend([
            {"count": 3, "type":"VEC3", "componentType":5126, "min":[0,0,0], "max":[1,1,1]},
            {"count": 3, "type":"SCALAR", "componentType":5123},
        ])
        meshes.append({"name":name,"primitives":[{"attributes":{"POSITION":pos},"indices":idx,"mode":4}]})
        nodes.append({"name":name,"mesh":i})
    gltf={"asset":{"version":"2.0"},"scene":0,"scenes":[{"nodes":list(range(len(nodes)))}],"nodes":nodes,"meshes":meshes,"accessors":accessors}
    path.write_text(json.dumps(gltf),encoding='utf-8')


def labels(ir):
    return sorted({x['semantic_candidate']['label'] for x in ir['semantic_ir']['candidates']})


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',default='benchmarks/model2ir/family-v0.1.json')
    ap.add_argument('--out',default='benchmark-artifacts/model2ir-family-v01')
    args=ap.parse_args()
    manifest=json.loads(Path(args.manifest).read_text())
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    cases={
        'long_hair_dress':['Body','Head','Long_Hair','Dress'],
        'short_hair_dress':['Body','Head','Short_Hair','Dress'],
        'long_hair_coat':['Body','Head','Long_Hair','Coat'],
        'body_book':['Body','Head','Book'],
        'body_crown':['Body','Head','Crown'],
        'body_magic_ring':['Body','Head','Magic_Ring'],
        'body_only':['Body','Head'],
        'body_tail':['Body','Head','Tail'],
        'body_wing':['Body','Head','Wing'],
    }
    results={}
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for case,names in cases.items():
            p=td/f'{case}.gltf'; make_gltf(p,names)
            ir=extract_ir(p); results[case]=ir
            (out/f'{case}.json').write_text(json.dumps(ir,indent=2)+'\n')

    pairs=[]
    for fam in manifest['families']:
        c=fam['cases']
        base=c[0]
        for other in c[1:]:
            d=diff_ir(results[base],results[other])
            pairs.append({'family':fam['id'],'a':base,'b':other,'diff':d})

    unresolved={case:[c['name'] for c in ir['semantic_ir']['unresolved']] for case,ir in results.items() if ir['semantic_ir']['unresolved']}
    gap_report={
        'schema':'model2ir-schema-gap-report/v0.1',
        'family_count':len(manifest['families']),
        'case_count':len(results),
        'pairwise_diff_count':len(pairs),
        'semantic_labels_by_case':{k:labels(v) for k,v in results.items()},
        'unresolved_by_case':unresolved,
        'observed_gaps':[
            {'field':'hair.style_or_length','status':'missing','evidence':'long_hair vs short_hair collapse to label hair'},
            {'field':'garment.subtype','status':'missing','evidence':'dress vs coat collapse to label garment'},
            {'field':'bodyplan.extra_appendages','status':'missing','evidence':'tail and wing remain unresolved in v0.1'},
            {'field':'semantic_relations','status':'partial','evidence':'name-only extraction cannot infer held_by/attached_to/surrounds'},
        ],
        'next_schema_targets':['hair subtype/shape','garment subtype/layer','extra appendages','attachment relations','material semantic evidence'],
        'policy':'gaps are evidence for schema/extractor evolution; unresolved is preferred over hallucinated labels',
    }
    (out/'pairwise-diffs.json').write_text(json.dumps(pairs,indent=2)+'\n')
    (out/'schema-gap-report.json').write_text(json.dumps(gap_report,indent=2)+'\n')
    assert any('Tail' in xs for xs in unresolved.values())
    assert any('Wing' in xs for xs in unresolved.values())
    print(json.dumps({'ok':True,'cases':len(results),'pairs':len(pairs),'gaps':len(gap_report['observed_gaps'])}))

if __name__=='__main__': main()
