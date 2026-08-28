from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from agent_core.realm_fabric import RealmFabricStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


class ControllerService:
    """Governed ONE control-plane dispatcher for Node actions.

    This service does not execute Node actions itself. It validates the target
    against the live Realm Node Map and translates a controller request into the
    existing agentos.node-task/v0.1 queue contract consumed by Thin Clients.
    """

    REQUEST_SCHEMA = 'agentos.controller-dispatch/v0.1'
    RECEIPT_SCHEMA = 'agentos.controller-dispatch-receipt/v0.1'

    def __init__(self, fabric: RealmFabricStore):
        self.fabric = fabric

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError('controller request must be an object')
        schema = request.get('schema')
        if schema not in (None, self.REQUEST_SCHEMA):
            raise ValueError('invalid controller dispatch schema')

        node_id = str(request.get('node_id') or request.get('target_node') or '').strip()
        action = str(request.get('action') or request.get('capability') or '').strip()
        if not node_id:
            raise ValueError('node_id is required')
        if not action:
            raise ValueError('action is required')

        node_map = self.fabric.node_registry.node_map()
        matches = [node for node in node_map.get('nodes', []) if node.get('node_id') == node_id]
        if not matches:
            raise KeyError(node_id)
        node = matches[0]
        if node.get('status') != 'online':
            raise ValueError(f'target node is not online: {node_id}')

        advertised = {str(x) for x in (node.get('capabilities') or []) if str(x)}
        if action not in advertised:
            raise ValueError(f'target node does not advertise capability: {action}')

        task_id = str(request.get('task_id') or ('task-' + uuid.uuid4().hex))
        payload = request.get('payload')
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError('payload must be an object')

        reserved = {'schema', 'task_id', 'action', 'node_id', 'target_node', 'capability', 'payload'}
        passthrough = {key: value for key, value in request.items() if key not in reserved}
        task = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'action': action,
            **payload,
            **passthrough,
        }
        queued = self.fabric.queue_task(node_id, task)
        return {
            'schema': self.RECEIPT_SCHEMA,
            'ok': True,
            'controller_entered': True,
            'dispatch_id': 'dispatch-' + uuid.uuid4().hex,
            'node_id': node_id,
            'action': action,
            'task_id': task_id,
            'queued_at': queued.get('queued_at') or _utc_now(),
            'queue_schema': queued.get('schema'),
            'node_status': node.get('status'),
            'advertised_capability': True,
        }
