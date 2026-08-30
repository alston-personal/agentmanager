#!/usr/bin/env python3
from __future__ import annotations

import argparse, json
from pathlib import Path
from model2ir import extract_ir


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cesium', required=True)
    ap.add_argument('--negative', required=True)
    ap.add_argument('--out', required=True)
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True, exist_ok=True)

    human=extract_ir(args.cesium)
    sem=human['semantic_evidence_v03']
    labels=set(sem['parts'])
    expected={'torso','left_arm','right_arm','left_leg','right_leg','neck'}
    missing=sorted(expected-labels)
    assert sem['body_plan']['kind']=='humanoid', sem['body_plan']
    assert len(missing) <= 1, missing
    assert sem['skeleton']['joint_count'] >= 10
    assert human['reversibility']['lossless'] is False

    negative=extract_ir(args.negative)
    nsem=negative['semantic_evidence_v03']
    assert nsem['body_plan']['kind'] != 'humanoid', nsem['body_plan']

    report={
      'schema':'model2ir-external-semantic-regression/v0.3',
      'human':{
        'body_plan':sem['body_plan'],
        'labels':sorted(labels),
        'joint_count':sem['skeleton']['joint_count'],
        'missing_expected':missing,
      },
      'negative':{
        'body_plan':nsem['body_plan'],
        'labels':sorted(nsem['parts']),
        'joint_count':nsem['skeleton']['joint_count'],
      },
      'gate':{
        'human_detected':True,
        'false_humanoid_avoided':True,
        'external_not_misreported_lossless':True,
        'status':'PASS',
      }
    }
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['gate']))
if __name__=='__main__': main()
