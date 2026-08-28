from __future__ import annotations

import secrets
from typing import Any

from agent_core.realm_fabric import RealmFabricStore


CONTROLLER_ACTION_CAPABILITY = {
    'agent.surface.inspect': 'agent.surface.inspect',
    'agent.session.discover': 'agent.session.discover',
    'agent.session.inspect': 'agent.session.inspect',
    'agent.context.harvest': 'agent.context.harvest',
    'desktop.session.inspect': 'desktop.session.inspect',
    'desktop.windows.inspect': 'desktop.windows.inspect',
    'desktop.screenshot': 'desktop.screenshot',
    'desktop.open_url': 'desktop.open_url',
}


class ControllerService:
    """Governed controller-side facade for ONE.

    This intentionally exposes only low-risk/read-oriented actions in v0.1.
    Arbitrary shell, writes, keyboard/mouse input and context injection stay
    outside the controller surface until a stronger approval/scoping contract
    exists.
    """

    def __init__(self, fabric: RealmFabricStore):
        self.fabric = fabric

    def realm(self) -> dict[str, Any]:
        node_map = self.fabric.node_registry.node_map()
        return {
            'schema': 'agentos.controller-realm/v0.1',
            'realm_id': node_map.get('realm_id'),
            'node_count': node_map.get('node_count', 0),
            'online_node_count': node_map.get('online_node_count', 0),
            'realm_capabilities': list(node_map.get('realm_capabilities') or []),
            'realm_tool_presence': list(node_map.get('realm_tool_presence') or []),
            'realm_surface_providers': list(node_map.get('realm_surface_providers') or []),
        }

    def nodes(self) -> dict[str, Any]:
        return self.fabric.node_registry.node_map()

    def node(self, node_id: str) -> dict[str, Any]:
        node_id = str(node_id or '').strip()
        if not node_id:
            raise ValueError('node_id is required')
        nodes = list(self.nodes().get('nodes') or [])
        node = next((item for item in nodes if item.get('node_id') == node_id), None)
        if node is None:
            raise KeyError(node_id)
        return node

    def _existing_task(self, task_id: str) -> dict[str, Any] | None:
        data = self.fabric.load()
        receipt = (data.get('receipts') or {}).get(task_id)
        if isinstance(receipt, dict):
            return {
                'state': 'completed',
                'node_id': receipt.get('node_id'),
                'action': receipt.get('action'),
                'queued_at': None,
            }
        for queued_node_id, queue in (data.get('tasks') or {}).items():
            for task in queue or []:
                if isinstance(task, dict) and task.get('task_id') == task_id:
                    return {
                        'state': 'queued',
                        'node_id': queued_node_id,
                        'action': task.get('action'),
                        'queued_at': task.get('queued_at'),
                    }
        return None

    def dispatch(self, node_id: str, request: dict[str, Any]) -> dict[str, Any]:
        node = self.node(node_id)
        if node.get('status') != 'online':
            raise ValueError(f'node is not online: {node_id}')
        action = str(request.get('action') or '').strip()
        required_capability = CONTROLLER_ACTION_CAPABILITY.get(action)
        if required_capability is None:
            raise PermissionError(f'controller action not permitted: {action}')
        capabilities = set(node.get('capabilities') or [])
        if required_capability not in capabilities:
            raise ValueError(f'node lacks capability: {required_capability}')

        task_id = str(request.get('task_id') or '').strip() or 'ctl_' + secrets.token_hex(12)
        existing = self._existing_task(task_id)
        if existing is not None:
            if existing.get('node_id') != node_id or existing.get('action') != action:
                raise ValueError(f'task_id already belongs to another request: {task_id}')
            return {
                'schema': 'agentos.controller-dispatch/v0.1',
                'ok': True,
                'node_id': node_id,
                'task_id': task_id,
                'action': action,
                'queued_at': existing.get('queued_at'),
                'state': existing.get('state'),
                'reused': True,
            }

        task: dict[str, Any] = {
            'schema': 'agentos.node-task/v0.1',
            'task_id': task_id,
            'action': action,
            'cognition_ids_used': list(request.get('cognition_ids_used') or []),
        }
        for key in ('provider', 'session_id', 'request_id', 'payload', 'url', 'quality'):
            if key in request:
                task[key] = request[key]
        queued = self.fabric.queue_task(node_id, task)
        return {
            'schema': 'agentos.controller-dispatch/v0.1',
            'ok': True,
            'node_id': node_id,
            'task_id': task_id,
            'action': action,
            'queued_at': queued.get('queued_at'),
            'state': 'queued',
            'reused': False,
        }

    def discover(self, node_id: str) -> dict[str, Any]:
        return self.dispatch(node_id, {'action': 'agent.surface.inspect'})

    def receipt(self, task_id: str) -> dict[str, Any]:
        task_id = str(task_id or '').strip()
        if not task_id:
            raise ValueError('task_id is required')
        receipt = self.fabric.get_receipt(task_id)
        if receipt is None:
            raise KeyError(task_id)
        return receipt
