from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPERIENCE_SCHEMA = 'agentos.product-experience/v0.1'
VALID_STATES = {'observed', 'validated_candidate', 'trusted', 'canonical'}
VALID_KINDS = {'rule', 'skill', 'pattern', 'transform', 'recovery', 'heuristic'}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


@dataclass
class ProductExperienceStore:
    product_id: str
    data_root: Path | None = None

    def __post_init__(self) -> None:
        product = str(self.product_id or '').strip()
        if not product:
            raise ValueError('product_id is required')
        self.product_id = product
        root = self.data_root or Path(os.environ.get('AGENT_DATA_ROOT', '/home/ubuntu/agent-data'))
        self.data_root = Path(root).expanduser()
        self.path = self.data_root / 'experience' / f'{self.product_id}.json'

    def _empty(self) -> dict[str, Any]:
        return {
            'schema': EXPERIENCE_SCHEMA,
            'product_id': self.product_id,
            'revision': 0,
            'updated_at': None,
            'units': {},
            'metrics': {
                'promoted_units_total': 0,
                'validated_candidates_total': 0,
                'reuse_hits_total': 0,
                'reuse_success_total': 0,
                'regressions_prevented_total': 0,
            },
        }

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        payload = json.loads(self.path.read_text(encoding='utf-8'))
        if payload.get('schema') != EXPERIENCE_SCHEMA:
            raise ValueError(f'invalid product experience store: {self.path}')
        if str(payload.get('product_id') or '') != self.product_id:
            raise ValueError('product experience store targets another product')
        payload.setdefault('units', {})
        payload.setdefault('metrics', self._empty()['metrics'])
        return payload

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload['revision'] = int(payload.get('revision') or 0) + 1
        payload['updated_at'] = _utc_now()
        tmp = self.path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.path)

    def upsert_candidate(
        self,
        *,
        experience_id: str,
        kind: str,
        claim: str,
        scope: str,
        source_experience: list[str],
        validation: list[str] | None = None,
        confidence: float = 0.5,
        state: str = 'observed',
        recovery: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        experience_id = str(experience_id or '').strip()
        if not experience_id:
            raise ValueError('experience_id is required')
        if kind not in VALID_KINDS:
            raise ValueError(f'invalid experience kind: {kind}')
        if state not in VALID_STATES:
            raise ValueError(f'invalid experience state: {state}')
        if not claim or not scope:
            raise ValueError('claim and scope are required')

        payload = self.load()
        existing = dict((payload.get('units') or {}).get(experience_id) or {})
        revision = int(existing.get('revision') or 0) + 1
        unit = {
            'id': experience_id,
            'revision': revision,
            'kind': kind,
            'claim': claim,
            'scope': scope,
            'state': state,
            'source_experience': sorted({str(x) for x in source_experience if str(x)}),
            'validation': sorted({str(x) for x in (validation or []) if str(x)}),
            'confidence': max(0.0, min(float(confidence), 1.0)),
            'recovery': dict(recovery or {}),
            'reuse': existing.get('reuse') or {'hits': 0, 'successes': 0, 'last_used_at': None},
            'created_at': existing.get('created_at') or _utc_now(),
            'updated_at': _utc_now(),
        }
        payload['units'][experience_id] = unit
        if state == 'validated_candidate' and existing.get('state') != 'validated_candidate':
            payload['metrics']['validated_candidates_total'] = int(payload['metrics'].get('validated_candidates_total') or 0) + 1
        if state in {'trusted', 'canonical'} and existing.get('state') not in {'trusted', 'canonical'}:
            payload['metrics']['promoted_units_total'] = int(payload['metrics'].get('promoted_units_total') or 0) + 1
        self.save(payload)
        return unit

    def record_reuse(self, experience_id: str, *, success: bool, prevented_regression: bool = False) -> dict[str, Any]:
        payload = self.load()
        unit = (payload.get('units') or {}).get(experience_id)
        if not unit:
            raise KeyError(experience_id)
        reuse = dict(unit.get('reuse') or {})
        reuse['hits'] = int(reuse.get('hits') or 0) + 1
        reuse['successes'] = int(reuse.get('successes') or 0) + (1 if success else 0)
        reuse['last_used_at'] = _utc_now()
        unit['reuse'] = reuse
        unit['updated_at'] = _utc_now()
        payload['units'][experience_id] = unit
        payload['metrics']['reuse_hits_total'] = int(payload['metrics'].get('reuse_hits_total') or 0) + 1
        if success:
            payload['metrics']['reuse_success_total'] = int(payload['metrics'].get('reuse_success_total') or 0) + 1
        if prevented_regression:
            payload['metrics']['regressions_prevented_total'] = int(payload['metrics'].get('regressions_prevented_total') or 0) + 1
        self.save(payload)
        return unit

    def promote(self, experience_id: str, *, target_state: str, evidence: list[str]) -> dict[str, Any]:
        if target_state not in {'trusted', 'canonical'}:
            raise ValueError('promotion target must be trusted or canonical')
        payload = self.load()
        unit = (payload.get('units') or {}).get(experience_id)
        if not unit:
            raise KeyError(experience_id)
        if unit.get('state') != 'validated_candidate' and target_state == 'trusted':
            raise ValueError('trusted promotion requires validated_candidate state')
        if target_state == 'canonical' and unit.get('state') not in {'trusted', 'canonical'}:
            raise ValueError('canonical promotion requires trusted state')
        reuse = unit.get('reuse') or {}
        if int(reuse.get('hits') or 0) < 1 or int(reuse.get('successes') or 0) < 1:
            raise ValueError('promotion requires successful independent reuse evidence')
        unit['state'] = target_state
        unit['validation'] = sorted(set(unit.get('validation') or []) | {str(x) for x in evidence if str(x)})
        unit['updated_at'] = _utc_now()
        payload['units'][experience_id] = unit
        payload['metrics']['promoted_units_total'] = int(payload['metrics'].get('promoted_units_total') or 0) + 1
        self.save(payload)
        return unit
