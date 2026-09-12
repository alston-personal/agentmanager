#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path
from model2ir import extract_ir, stabilize_external_ir, compile_reversible_gltf, ir_digest


def verify_candidate_storage(raw, candidate, output):
    """Regression-only check: preserve candidates without asserting truth."""
    assert candidate['truth_status'] == 'candidate'
    try:
        compile_reversible_gltf(raw, candidate)
    except ValueError as exc:
        assert 'refusing to embed truth_status' in str(exc), str(exc)
    else:
        raise AssertionError('candidate silently promoted to canonical')
    output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + '\n')
    recovered = json.loads(output.read_text())
    assert recovered == candidate
    assert ir_digest(recovered) == ir_digest(candidate)
    return {'candidate_json_exact': True, 'candidate_digest': ir_digest(candidate),
            'canonical_embedding_rejected': True, 'canonical_promotion': False}


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

    # Deterministic projection is not semantic confirmation. Preserve it as JSON;
    # canonical carrier reversibility is tested separately with declared fixtures.
    raw=json.loads(Path(args.input).read_text())
    storage=verify_candidate_storage(raw, ca, out/'candidate-ir.json')

    report={
      'schema':'model2ir-stabilized-import-regression/v0.9.2',
      'source_lossless':False,
      'candidate_digest':ir_digest(ca),
      'deterministic_initial_projection':True,
      'candidate_storage':storage,
      'candidate_body_plan':ca['body_plan'],
      'candidate_parts':[p['id'] for p in ca['parts']],
      'unresolved_count':len(ca['unresolved']),
      'gate':{'status':'PASS','candidate_repeatability':1.0,'candidate_json_roundtrip':1.0,'canonical_embedding_rejected':True},
    }
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['gate']))
if __name__=='__main__': main()
