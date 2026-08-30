#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path
from model2ir import extract_ir, stabilize_external_ir, compile_reversible_gltf, score_roundtrip, ir_digest


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out', required=True)
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)

    # Repeated external extraction must be deterministic.
    a=extract_ir(args.input)
    b=extract_ir(args.input)
    ca=stabilize_external_ir(a)
    cb=stabilize_external_ir(b)
    assert ca == cb
    assert ir_digest(ca) == ir_digest(cb)
    assert a['reversibility']['lossless'] is False
    assert ca['truth_status']=='candidate'

    # Stabilize the external model by embedding the candidate IR into its glTF carrier.
    raw=json.loads(Path(args.input).read_text())
    carrier=compile_reversible_gltf(raw, ca)
    stable_path=out/'stabilized.gltf'
    stable_path.write_text(json.dumps(carrier,ensure_ascii=False,indent=2)+'\n')
    recovered=extract_ir(stable_path)
    assert recovered['reversibility']['lossless'] is True
    assert recovered['canonical_ir'] == ca
    assert recovered['canonical_ir_digest'] == ir_digest(ca)
    score=score_roundtrip(ca,recovered)
    assert score['lossless_reversible'] is True
    assert score['canonical_difference_count']==0

    report={
      'schema':'model2ir-stabilized-import-regression/v0.4',
      'source_lossless':False,
      'candidate_digest':ir_digest(ca),
      'deterministic_initial_projection':True,
      'stabilized_lossless':True,
      'roundtrip':score,
      'candidate_body_plan':ca['body_plan'],
      'candidate_parts':[p['id'] for p in ca['parts']],
      'unresolved_count':len(ca['unresolved']),
      'gate':{'status':'PASS','candidate_repeatability':1.0,'post_stabilization_reversibility':1.0},
    }
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['gate']))
if __name__=='__main__': main()
