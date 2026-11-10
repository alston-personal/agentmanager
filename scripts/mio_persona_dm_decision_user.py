#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mio_persona_social_loop_user import persona_context
from agentos_node.antigravity_relay import AntigravityRelayClient

RELAY_ROOT=Path('/home/ubuntu/agent-data/runtime/mio-antigravity-relay')

def deterministic_ir_fallback(dm: dict, context: dict, relay_status: str) -> dict:
    message=str(dm.get('message') or '').strip()
    relation=str(dm.get('relationship_status') or 'unknown')
    relationship_context=dm.get('relationship_context') if isinstance(dm.get('relationship_context'),dict) else {}
    ir=context.get('current_ir') or {}
    invariants=ir.get('invariants') or {}
    current=ir.get('current_self') or {}
    principles=current.get('interaction_principles') or []
    no_false=bool(invariants.get('no_false_autobiography'))
    travel_terms=('旅行','旅遊','假期','去哪裡玩','去哪玩')
    scenery_topics={str(x.get('topic') or '') for x in (current.get('interests_with_evidence') or []) if isinstance(x,dict)}
    if no_false and any(t in message for t in travel_terms) and '散步、風景與日常觀察' in scenery_topics:
        return {
            'decision':'reply',
            'text':'沒有安排旅行耶，最近反而一直在想海邊跟散步這種小行程。你有去哪裡嗎？',
            'position':'uncertain',
            'reason_category':'question',
            'memory_basis':'Current IR forbids false autobiography; it does contain evidence-backed interest in walking, scenery, and a recent sea-side theme.',
            'relationship_basis':(
                'No prior relationship record found; treat as a new/unknown interaction and keep the reply light.'
                if relation in ('unknown','unknown_new_interaction','')
                else 'Existing relationship stage '+relation+'; preserve continuity without assuming greater intimacy than recorded.'
            ),
            'consistency_check':'pass',
            'decision_source':'deterministic_ir_fallback',
            'relay_status':relay_status,
        }
    return {
        'decision':'no_reply',
        'text':None,
        'position':'no_reply',
        'reason_category':'other',
        'memory_basis':'Deterministic fallback only replies when a truthful low-risk response is directly grounded in current IR.',
        'relationship_basis':'Relationship is '+relation+'.',
        'consistency_check':'insufficient_context',
        'decision_source':'deterministic_ir_fallback',
        'relay_status':relay_status,
    }

def decide(dm: dict) -> dict:
    context=persona_context()
    prompt=f"""You are making a PRIVATE direct-message decision for 澪 / Mio (@mio.milkcat).
Return JSON only, no markdown.

Use Mio's CURRENT persona IR as the primary self-model.
This is a private DM, but all identity/memory/truth boundaries still apply.

Critical rules:
- Decide reply or no_reply first; silence is valid.
- Do not invent autobiographical experiences. If asked about travel, food, places, purchases, injuries, meetings, or other lived experiences, only claim what exists in supplied persona memory/events.
- Mio is a virtual AI persona; do not falsely imply a real human body or real-world travel occurred.
- Do not volunteer implementation details unless directly relevant.
- Be warm but not automatically agreeable.
- New/unknown relationships should not be treated as intimate.
- Payment, contracts, account security and sensitive identity decisions remain human-reserved.
- Keep a reply short and natural, Traditional Chinese unless the sender clearly uses another language.
- If context is insufficient but a truthful lightweight reply is possible, you may reply by reframing toward canonical virtual-life/current-interest context rather than fabricating.
- If replying would require fabrication or unsafe assumptions, choose no_reply.

Current Persona context:
{json.dumps(context,ensure_ascii=False)}

DM:
{json.dumps(dm,ensure_ascii=False)}

Required schema:
{{
  "decision":"reply"|"no_reply",
  "text":"..."|null,
  "position":"agree|partly_agree|disagree|uncertain|playful_only|no_reply",
  "reason_category":"relationship|question|conversation|boundary|low_value|other",
  "memory_basis":"brief private basis grounded in supplied IR/memory",
  "relationship_basis":"brief private basis; say unknown/new if no relationship evidence",
  "consistency_check":"pass|insufficient_context"
}}
"""
    client=AntigravityRelayClient(RELAY_ROOT)
    cap=client.submit(
        project_id='sunlake-milkcat-persona-dm',
        canonical_ir={
            'goal':'Let Mio decide whether and how to reply to a private Threads DM without fabricating lived experience.',
            'constraints':['current Persona IR is primary','no false autobiography','no hidden implementation disclosure','human-reserved boundaries remain guarded']
        },
        instruction=prompt,
        workspace='/home/ubuntu/agentmanager',
    )
    for _ in range(75):
        receipt=client.receipt(cap['capsule_id'])
        if receipt:
            if not receipt.get('ok'):
                provider=str(receipt.get('provider') or 'unknown')[:24]
                code=str(receipt.get('returncode') if receipt.get('returncode') is not None else 'none')[:12]
                timed_out=str(bool(receipt.get('timed_out'))).lower()
                err=str(receipt.get('error') or '')
                low=err.lower()
                if 'no authorized local antigravity executor' in low:
                    category='executor_not_found'
                elif 'workspace unavailable' in low:
                    category='workspace_unavailable'
                elif 'permission' in low:
                    category='permission_denied'
                elif 'quota' in low or 'rate' in low:
                    category='quota_or_rate'
                elif 'login' in low or 'auth' in low:
                    category='auth'
                else:
                    category='other'
                etype='none'
                import re
                m=re.match(r'^([A-Za-z][A-Za-z0-9_]{0,50}(?:Error|Exception)):',err)
                if m: etype=m.group(1)
                relay_status='provider='+provider+':returncode='+code+':timed_out='+timed_out+':category='+category+':error_type='+etype
                return deterministic_ir_fallback(dm,context,relay_status)
            raw=str(receipt.get('stdout') or '')
            decoder=json.JSONDecoder()
            for i,ch in enumerate(raw):
                if ch!='{': continue
                try: obj,_=decoder.raw_decode(raw[i:])
                except Exception: continue
                if isinstance(obj,dict) and obj.get('decision') in {'reply','no_reply'}:
                    return obj
            raise RuntimeError('mio_dm_decision_json_missing')
        time.sleep(2)
    raise TimeoutError('mio_dm_decision_timeout')

def main() -> int:
    dm=json.load(sys.stdin)
    out=decide(dm)
    print(json.dumps(out,ensure_ascii=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
